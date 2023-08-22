# DNA Center - Fusion Router Auto-Provisioning

This repository contains sample code for automatically configuring & provisioning a fusion router for an SDA Deployment. This code assumes that the fusion router is managed by DNA Center & configuration templates may be pushed to it.

Fusion router configuration generated from this script:

- VRF
- VLAN interface
- BGP peering

The above details are generated based on current state of border router configurartion. Border routers to use are specified at time of script configuration.

## Contacts

- Matt Schmitz (<mattsc@cisco.com>)

## Solution Components

- DNA Center
- Python / Flask

## Installation/Configuration

### **Step 1 - Clone repo:**

```bash
git clone <repo_url>
```

### **Step 2 - Install required dependancies:**

```bash
pip install -r requirements.txt
```

### **Step 3 - Provide DNA Center Information**

In order to use this script, certain environment variables must be provided to store DNA Center configuration. These variables may also be provided via a local `.env` file.

See the below example for required variable names & descriptions:

```
#
# DNA Center configuration
#

# IP or host name of DNA Center
DNAC_HOST=

# DNAC credentials for API Access
DNAC_USER=
DNAC_PASSWORD=

# Name of project to hold templates 
DNAC_PROJECT_NAME=
DNAC_TEMPLATE_NAME=
```

> Note: DNA center project name must match an existing project. Template will be created with the provided name, if one does not already exist.

### **Step 4 - Provide SDA configuration**

Target SDA configuration is provided by `config.yaml` (sample template available at `example-config.yaml`).

- Specify which border nodes that the fusion router will need to peer with.
- Provide the name of the fusion router node that will be provisioned.
- Define each VRF to be provisioned, including route distinguisher, VLAN assignments, and which route targets to import

```yaml
# List border node hostnames to pull configuration from
border_nodes:
 - Router01
 - Router02
 - Router03

# Specify fusion router hostname to provision
fusion_router: FusionRouter01

# Define VRFs to provision on fusion router
vrfs:
  # Each node is the VRF name
  RED:
    # Set VRF RD
    rd: 1:100
    # Specify VLAN interfaces to add to this VRF 
    vlans:
     - 1001
     - 1003
    # Specify route targets to import
    import: 
     - 1:200
     - 1:500
  # Example 2:
  BLUE:
    rd: 1:200
    vlans:
     - 1000
     - 1002
    import: 
     - 1:100
     - 1:500
```

## Usage

### Running locally

Run the application with the following command:

```
python3 provision_fusion.py
```

The script will first collect information from DNA Center, then generate the configuration needed to provision the fusion router. Before uploading the new template to DNA Center, the script will prompt to optionally display & review the configuration changes.

# Related Sandbox

- [Cisco DNA Center Lab](https://devnetsandbox.cisco.com/RM/Diagram/Index/b8d7aa34-aa8f-4bf2-9c42-302aaa2daafb?diagramType=Topology)

# Screenshots

### Demo of script

![/IMAGES/demo.gif](/IMAGES/demo.gif)

### LICENSE

Provided under Cisco Sample Code License, for details see [LICENSE](LICENSE.md)

### CODE_OF_CONDUCT

Our code of conduct is available [here](CODE_OF_CONDUCT.md)

### CONTRIBUTING

See our contributing guidelines [here](CONTRIBUTING.md)

#### DISCLAIMER

<b>Please note:</b> This script is meant for demo purposes only. All tools/ scripts in this repo are released for use "AS IS" without any warranties of any kind, including, but not limited to their installation, use, or performance. Any use of these scripts and tools is at your own risk. There is no guarantee that they have been through thorough testing in a comparable environment and we are not responsible for any damage or data loss incurred with their use.
You are responsible for reviewing and testing any scripts you run thoroughly before use in any non-testing environment.
