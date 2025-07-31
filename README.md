# ScaleApp
Retrieve and save data from industrial scales into an Excel file.

## Case scenario & Problem
The stakeholder operates a business that buys materials on a large scale. For that, they have two industrial scales that weigh the materials; therefore, they can pay accordingly to the amount being offered.

The user must handle client interactions, store materials, pay the seller, and track transaction history daily. To ensure they always have the correct data for all transactions, the user requested a simple desktop system that reads and automatically saves all scale inputs for their records.

The computer and scales are not physically placed close to each other. Having that in mind, an Ethernet connection would be a better solution than a simple COM connection through RS-232 wires. 

## The hardware
The stakeholder has two WeighTech industrial scales: WT1000 and WT3000i. (More details: https://www.weightech.com.br/)

The first one uses an RS-232 to connect to the WiFi through a USR-W610 converter device. The second one connects to a USR-TCP232-306 device using RS-232 and Ethernet wires.

## The software
The system consists of a server that is responsible for identifying the IP addresses that the scales connect to. Having that information, the system then connects to the scales and continuously reads the input of stable weight data, which is written to an Excel file for their records.

For testing code purposes, I developed a scale simulator. The code acts as a client of the previously mentioned server and generates random data to send to the server. That is available as "scaleSimulatorWiFi.py".

# How to run
(Work in progress)
