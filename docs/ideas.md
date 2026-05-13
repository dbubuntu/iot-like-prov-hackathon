# Brief
The project will be a demo to show an IoT-like provisioning mechanism for an emulated device.
There are the following components
1. Emulated IoT device (Linux based)
2. Provisioning server
3. Mobile app
The idea is that the server authenticates the device with mutual trust.

# Components
More details about the components
1. DEVICE: Emulated IoT device (Linux based) 
Let's call it DEVICE from now on.
It is emulated on a LXD VM or container (whatever is best).
It needs to access both BT and WIFI from the host.
The DEVICE has initially no connection, so the idea is that using the mobile APP, the user connects to the device. The APP scans WIFI Access Points and the user with the APP tells the DEVICE to connect using WIFI.
The DEVICE will connect to the SERVER and receive a token.
The token will be shown on the terminal so that the APP scans it and sends it back to the SERVER to be approved.
So the DEVICE needs the following features:
- BT listening server
- WIFI connection
- A TUI to interact with it. It will eventually show a QR code on terminal that the APP will scan.

2. SERVER: Provisioning server
Let's call it SERVER from now on.
The SERVER receives approva

3. APP: Mobile app
Let's call it APP from now on.

# Process
## Pre-requisites
- The SERVER is running and listening for connections (known IP and PORT)
- The DEVICE has no initial connectivity (no IP). It can only be accessed via console (LXD?)
- The APP has the SERVER IP and PORT in variables

## DEVICE connection
The goal is to provide the DEVICE with and IP and connection to the SERVER via WIFI.
1. The DEVICE application starts and listens for BT incoming connections.
2. The user opens the APP
3. The APP connects to the DEVICE using BT (to be decided if the DEVICE is pre-paired or if it's done in the APP)
4. When there is an incoming connection, the DEVICE approves it
5. The APP scans WIFI access points, the user selects one and the APP sends it to the DEVICE
6. The DEVICE receives the access point and connects to it
7. The DEVICE sends its new IP address to the APP
Now, the DEVICE has IP and connectivity to the SERVER

## Enrolment
1. The APP knows the IP of the DEVICE and sends a request to the SERVER
2. The SERVER sends a token to the DEVICE
3. The DEVICE shows a QR code on the TUI
4. The user with the APP scans the QR code and sends it back to the SERVER to get approval
5. The SERVER receives the approval request and automatically approves it
6. The SERVER sends and ACK to the DEVICE

The DEVICE is provisioned

# Repo
All the project needs to be uploaded to a Github repo.



======

I want to create a project with the requirements below.
I'm going to create it developing with Zed, using OpenCode and connected to OpenRouter.
I want to create multiple agents that help me develop everything.
Create a well-defined spec that agents can understand.
Create the list of agents with skills needed.
Propose the folder structure too.
The project needs to be uploaded to a Github repo.
