"""
Copyright (c) 2023 Cisco and/or its affiliates.
This software is licensed to you under the terms of the Cisco Sample
Code License, Version 1.1 (the "License"). You may obtain a copy of the
License at
               https://developer.cisco.com/docs/licenses
All use of the material herein must be in accordance with the terms of
the License. All rights not expressly granted by the License are
reserved. Unless required by applicable law or agreed to separately in
writing, software distributed under the License is distributed on an "AS
IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express
or implied.
"""
import os
import re
import sys
from ipaddress import IPv4Network
from time import sleep

import yaml
from dnacentersdk import api
from dnacentersdk.exceptions import ApiError
from dotenv import load_dotenv
from jinja2 import Environment, FileSystemLoader
from rich import print
from rich.console import Console
from rich.panel import Panel
from rich.progress import track
from rich.prompt import Confirm
from schema import Schema, SchemaError

console = Console()

config_schema = Schema(
    {
        "border_nodes": [str],
        "fusion_router": str,
        "vrfs": {str: {"rd": str, "vlans": [int], "import": [str]}},
    }
)


# Load environment variables
load_dotenv()

# Load Jinja config templates
conf_templates = Environment(loader=FileSystemLoader("templates/"))

# Fetch DNAC config
DNAC_HOST = os.getenv("DNAC_HOST")
DNAC_USER = os.getenv("DNAC_USER")
DNAC_PASSWORD = os.getenv("DNAC_PASSWORD")
DNAC_PROJECT_NAME = os.getenv("DNAC_PROJECT_NAME")
DNAC_TEMPLATE_NAME = os.getenv("DNAC_TEMPLATE_NAME", "fusion_router_config")

# Validate environment variables are provided
if any(x is None for x in [DNAC_HOST, DNAC_USER, DNAC_PASSWORD, DNAC_PROJECT_NAME]):
    print("[red]Required environment variables not found.")
    print("Please configure: DNAC_HOST, DNAC_USER, DNAC_PASSWORD, DNAC_PROJECT_NAME")
    sys.exit(1)

global config


def checkTaskStatus(dnac, task: str) -> str:
    """
    General function to check DNA Center task status.
    """
    while True:
        print("Waiting for task to finish. Current status: Not Started")
        task_status = dnac.task.get_task_by_id(task.response.taskId)
        print(
            f"Waiting for task to finish. Current status: {task_status['response']['progress']}"
        )
        if task_status["response"]["endTime"]:
            print("[green][bold]Task finsished!")
            return task_status
        sleep(3)


def connectDNAC() -> api.DNACenterAPI | None:
    """
    Establish connection to DNAC
    """
    try:
        print(f"Attempting connection to {DNAC_HOST} as user {DNAC_USER}")
        with console.status("Connecting..."):
            dnac = api.DNACenterAPI(
                username=DNAC_USER,
                password=DNAC_PASSWORD,
                base_url=f"https://{DNAC_HOST}",
                verify=False,
            )
        print("[green]Connected to DNA Center!")
        return dnac
    except Exception as e:
        print("Failed to connect to DNA Center")
        print(f"Error: {e}")
        sys.exit(1)


def getProjectID(dnac: api.DNACenterAPI) -> str:
    """
    General function to locate DNA Center project identifier, which will be required to
    add/remove templates.
    """
    # Retrieve UUID for Template project
    print("Querying DNA Center for project list...")
    project = dnac.configuration_templates.get_projects(name=DNAC_PROJECT_NAME)
    project_id = project[0]["id"]
    return project_id


def getTemplateID(dnac: api.DNACenterAPI) -> str:
    """
    Looks up template ID by name
    """
    project = dnac.configuration_templates.get_projects(name=DNAC_PROJECT_NAME)
    if len(project[0]["templates"]) == 0:
        print("Project has no templates yet")
        template_id = None
        return
    for template in project[0]["templates"]:
        if template["name"] == DNAC_TEMPLATE_NAME:
            template_id = template["id"]
            break
        else:
            print(f"Template {DNAC_TEMPLATE_NAME} does not exist yet")
            template_id = None
            return
    print(f"Using template ID: {template_id}")
    return template_id


def uploadTemplate(
    dnac: api.DNACenterAPI, template_payload: str, device_info: dict
) -> str:
    """
    Create / Update DNA Center template
    """
    project_id = getProjectID(dnac)
    template_id = getTemplateID(dnac)
    device_types = []
    for device in device_info:
        device_types.append(
            {
                "productFamily": device_info[device]["family"],
                "productSeries": device_info[device]["series"],
            }
        )
    template_params = {
        "project_id": project_id,
        "name": DNAC_TEMPLATE_NAME,
        "softwareType": "IOS-XE",
        "deviceTypes": device_types,
        "payload": {"templateContent": template_payload},
        "version": "2",
        "language": "VELOCITY",
    }
    print("Uploading template to DNA Center...")
    # Push update if template exists
    if template_id:
        template_params["id"] = template_id
        dnac.configuration_templates.update_template(**template_params)
        # Allow DNAC a moment to update template
        sleep(3)
        print("Template updated.")
    # Create new if no existing template ID
    elif not template_id:
        dnac.configuration_templates.create_template(**template_params)
        # Allow DNAC a moment to create new template
        sleep(3)
        print("Template created.")
        template_id = getTemplateID(dnac)
    # Commit new template
    print("Committing new template version...")
    dnac.configuration_templates.version_template(
        comments="Commit via API", templateId=template_id
    )
    print("Template committed.")
    # Allow DNAC a moment...
    sleep(3)
    print("[green]Template ready!")
    return template_id


def deployTemplate(dnac: api.DNACenterAPI, template_id: str, device: dict) -> None:
    """
    Push new configuration template to all target devices.
    """
    print(f"Starting deployment to {config['fusion_router'][0]} at {device['ip']}")
    target_devices = []
    target_devices.append(
        {
            "id": device["ip"],
            "type": "MANAGED_DEVICE_IP",
            "params": {"device_ip": device["ip"]},
        }
    )
    deploy_template = dnac.configuration_templates.deploy_template(
        templateId=template_id,
        targetInfo=target_devices,
    )
    # Grab deployment UUID
    deploy_id = str(deploy_template.deploymentId).split(":")[-1].strip()
    # If any errors are generated, they are included in the deploymentId field
    # So let's validate that we actually have a valid UUID - otherwise assume error
    if not re.match("^.{8}-.{4}-.{4}-.{4}-.{12}$", deploy_id):
        print("[red]Error deploying template: ")
        print(deploy_template)
    print("[green]Deployment started!")
    with console.status("Checking deployment status...") as status:
        while True:
            # Monitor deployment status to see when it completes
            response = dnac.configuration_templates.get_template_deployment_status(
                deployment_id=deploy_id
            )
            if response["status"] == "SUCCESS" or response["status"] == "FAILURE":
                break
            else:
                status.update(f"Deployment status: {response['status']}")
                sleep(2)

    if response["status"] == "SUCCESS":
        print("[green][bold]Deployment complete!")
    if response["status"] == "FAILURE":
        print("[red][bold]Deployment Failed! See below for errors:")
        print(response)


def loadConfig() -> None:
    """
    Load configuration file
    """
    print("Loading config file...")
    global config
    with open("./config.yaml", "r") as file:
        with console.status("Processing..."):
            config = yaml.safe_load(file)
            try:
                config_schema.validate(config)
                print("[green]Config loaded!")
            except SchemaError as e:
                print("[red]Failed to validate config.yaml. Error:")
                print(e)
                sys.exit(1)


def getDNACDevices(dnac: api.DNACenterAPI) -> dict:
    """
    Retrieve DNA Center devices
    """
    print("Collecting device info...")
    hostnames = [device + ".*" for device in config["border_nodes"]]
    hostnames += [device + ".*" for device in config["fusion_router"]]
    devices = dnac.devices.get_device_list(hostname=hostnames)
    print(f"Got {len(devices.response)} devices.")
    device_info = {}
    for device in track(devices.response, description="Processing..."):
        device_info[device.hostname] = {}
        device_info[device.hostname]["ip"] = device["managementIpAddress"]
        device_info[device.hostname]["uuid"] = device["id"]
        device_info[device.hostname]["series"] = device["series"]
        device_info[device.hostname]["family"] = device["family"]
        for name in config["border_nodes"]:
            if name in device.hostname:
                device_info[device.hostname]["role"] = "BORDER"
        for name in config["fusion_router"]:
            if name in device.hostname:
                device_info[device.hostname]["role"] = "FUSION"
    print("[green]Done!")
    return device_info


def getBorderDeviceInfo(dnac: api.DNACenterAPI, devices: dict) -> dict:
    """
    Query border router info from SDA fabric
    """
    peers = {}
    print("Collecting border node configs...")
    for device in track(devices):
        if devices[device]["role"] == "BORDER":
            peer_info = dnac.sda.gets_border_device_detail(devices[device]["ip"])
            name = peer_info["name"]
            device_settings = peer_info["deviceSettings"]
            # Note: For now this assumes only 1 IP transit available/configured
            ext_settings = device_settings["extConnectivitySettings"][0]
            l3 = ext_settings["l3Handoff"]
            peers[name] = {}
            peers[name]["local_as"] = ext_settings["externalDomainProtocolNumber"]
            peers[name]["l3links"] = []
            for link in l3:
                link_info = {}
                link_info["remote_as"] = device_settings["internalDomainProtocolNumber"]
                link_info["network"] = IPv4Network(
                    link["remoteIpAddress"], strict=False
                ).network_address
                link_info["local_ip"] = link["remoteIpAddress"].split("/")[0]
                link_info["local_netmask"] = IPv4Network(
                    link["remoteIpAddress"], strict=False
                ).netmask
                link_info["remote_ip"] = link["localIpAddress"].split("/")[0]
                link_info["remote_netmask"] = IPv4Network(
                    link["localIpAddress"], strict=False
                ).netmask
                link_info["vlan_id"] = link["vlanId"]
                for vrf in config["vrfs"]:
                    for vlan in config["vrfs"][vrf]["vlans"]:
                        if vlan == link_info["vlan_id"]:
                            link_info["vrf_name"] = vrf
                            link_info["rd"] = config["vrfs"][vrf]["rd"]
                            link_info["import_rt"] = config["vrfs"][vrf]["import"]
                peers[name]["l3links"].append(link_info)
    print("[green]Done!")
    return peers


def generateFusionConfig(peers: dict) -> str:
    """
    Generate Fusion router config based on peer config
    """
    print("Generating fusion router config...")
    bgp_template = conf_templates.get_template("bgp.jinja2")
    bgp_peers_template = conf_templates.get_template("bgp_peers.jinja2")
    vlan_template = conf_templates.get_template("vlan_interface.jinja2")
    vrf_template = conf_templates.get_template("vrf.jinja2")

    local_as = None

    # Generate VLAN interface config first
    vlan_config = []
    for peer in track(peers, description="VLANs"):
        if not local_as:
            local_as = peers[peer]["local_as"]
        for link in peers[peer]["l3links"]:
            vlan_config.append(vlan_template.render(**link))

    # Generate VRF config
    vrf_config = []
    for vrf in track(config["vrfs"], description="VRFs "):
        vrf_def = config["vrfs"][vrf]
        vrf_config.append(
            vrf_template.render(
                vrf_name=vrf, rd=vrf_def["rd"], import_rt=vrf_def["import"]
            )
        )

    # Generate BGP Config
    vrfs = {}
    for peer in track(peers, description="BGP  "):
        for link in peers[peer]["l3links"]:
            vrf_name = link["vrf_name"]
            if not vrf_name in vrfs.keys():
                vrfs[vrf_name] = []
            vrfs[vrf_name].append(bgp_peers_template.render(link))
    bgp_config = bgp_template.render(local_as=local_as, bgp_vrfs=vrfs)

    print("[green]Configuration template generated!")
    final_config = "\r\n!\r\n".join(vrf_config)
    final_config += "\r\n!\r\n"
    final_config += "\r\n!\r\n".join(vlan_config)
    final_config += "\r\n"
    final_config += "!\r\n" + bgp_config

    return final_config


def main():
    print("")
    print(Panel.fit("  -- Start --  "))
    print("")

    print("")
    print(Panel.fit("Load Config File", title="Step 1"))
    loadConfig()

    print("")
    print(Panel.fit("Connect to DNA Center", title="Step 2"))
    dnac = connectDNAC()

    print("")
    print(Panel.fit("Collect Device Info", title="Step 3"))
    devices = getDNACDevices(dnac)

    print("")
    print(Panel.fit("Collect SDA Transit Config", title="Step 4"))
    peers = getBorderDeviceInfo(dnac, devices)

    print("")
    print(Panel.fit("Generate Fusion Router config", title="Step 5"))
    fusion_config = generateFusionConfig(peers)

    print("")
    print(Panel.fit("Validate Generated Config", title="Step 6"))
    if Confirm.ask("View generated configuration?"):
        with console.pager():
            console.print(fusion_config)

    print("")
    print(Panel.fit("Creating DNA Center Template", title="Step 7"))
    if not Confirm.ask("Upload template to DNA Center?"):
        print("\r\nQuitting...")
        sys.exit(0)
    template_id = uploadTemplate(dnac, fusion_config, devices)

    print("")
    print(Panel.fit("Deploy Fusion Router config", title="Step 8"))
    if not Confirm.ask("Proceed with deployment?"):
        print("\r\nQuitting...")
        sys.exit(0)
    for device in devices:
        if devices[device]["role"] == "FUSION":
            deployTemplate(dnac, template_id, devices[device])
            break

    print("")
    print(Panel.fit("  -- Finished --  "))
    print("")


if __name__ == "__main__":
    main()
