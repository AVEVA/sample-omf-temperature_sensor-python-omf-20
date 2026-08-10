# Temperature Sensor OMF 2.0 Python Sample

**Version:** 1.0.0

[![Build Status](https://dev.azure.com/AVEVA-VSTS/Cloud%20Platform/_apis/build/status%2Fproduct-readiness%2FCONNECT%2FAVEVA.sample-omf-temperature_sensor-python-omf-20?repoName=AVEVA%2Fsample-omf-temperature_sensor-python-omf-20&branchName=main)](https://dev.azure.com/AVEVA-VSTS/Cloud%20Platform/_build/latest?definitionId=25018&repoName=AVEVA%2Fsample-omf-temperature_sensor-python-omf-20&branchName=main)

This sample uses Open Message Format version 2.0 to send random sample values, assets and events to CONNECT (EAP or CDS), Edge Data Store, and/or PI Web API. As of now (last updated August 2026) OMF 2.0 is only supported in CONNECT EAP. The sample includes the code to send to all endpoints for the future, but only CONNECT EAP will work today. Once the sample is started, the assets are created, then the sample periodically collects (or generates) values for temperature until it reaches a specified number of values. At each interval it then sends that data to each of the configured OMF endpoints. It checks the value of the temperature sensor against a configured threshold. It will start and stop events based on where the value falls in the configured threshold and send those updates to each endpoint.

## To run this sample:

1. Clone the GitHub repository
1. Install required modules: `pip install -r requirements.txt`
1. Open the folder with your favorite IDE
1. Rename the placeholder config file [appsettings.placeholder.json](appsettings.placeholder.json) to appsettings.json
1. Update appsettings.json with the credentials for the enpoint(s) you want to send to. See [Configure endpoints and authentication](#configure-endpoints-and-authentication) below for additional details
1. Run program.py

## To test this sample:

### Option 1

1. Run test.py

### Option 2

1. Install pytest `pip install pytest`
1. Run `pytest program.py`

## Configure endpoints and authentication

The sample is configured using the file [appsettings.placeholder.json](appsettings.placeholder.json). Before editing, rename this file to `appsettings.json`. This repository's `.gitignore` rules should prevent the file from ever being checked in to any fork or branch, to ensure credentials are not compromised.

The application can be configured to send to any number of endpoints specified in the endpoints array within appsettings.json. In addition, there are three types of endpoints: CONNECT data services [Cds](#cds-endpoint-configuration), [EDS](#eds-endpoint-configurations), and [PI](#pi-endpoint-configuration). Each of the 3 types of enpoints are configured differently and their configurations are explained in the sections below.

### Cds endpoint configuration

An OMF ingress client must be configured. On our [AVEVA Learning](https://www.youtube.com/channel/UC333r4jIeHaY-rGgMjON54g) Channel on YouTube we have a video on [Creating an OMF Connection](https://www.youtube.com/watch?v=52lAnkGC1IM).

The format of the configuration for a CONNECTEAP endpoint is shown below along with descriptions of each parameter. Replace all parameters with appropriate values.

```json
{
  "Selected": true,
  "EndpointType": "CONNECTEAP",
  "ClientId": "PLACEHOLDER_REPLACE_WITH_CLIENT_ID",
  "ClientSecret": "PLACEHOLDER_REPLACE_WITH_CLIENT_SECRET",
  "TokenEndpoint": "https://identity.platform.connect.aveva.com/account/<accountid>/authentication/connect/token",
  "Endpoint": "https://platform.connect.aveva.com/api/account/<accountid>/omfIngress/<omfIngressId>/v1/messages",
  "VerifySSL": true,
  "UseCompression": true,
  "WebRequestTimeoutSeconds": 30
}
```

| Parameters               | Required | Type    | Description                                                                                                                                                      |
| ------------------------ | -------- | ------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Selected                 | required | boolean | Tells the application if the endpoint should be sent to                                                                                                          |
| EndpointType             | required | string  | The endpoint type. For Cds this will always be "CDS"                                                                                                             |
| Resource                 | required | string  | The endpoint for Cds if the namespace. If the tenant/namespace is located in NA, it is https://uswe.datahub.connect.aveva.com and if in EMEA, it is https://euno.datahub.connect.aveva.com  |
| NamespaceID              | required | string  | The name of the Namespace in Cds that is being sent to                                                                                                           |
| Tenant                   | required | string  | The Tenant ID of the Tenant in Cds that is being sent to                                                                                                         |
| ClientId                 | required | string  | The client ID that is being used for authenticating to Cds                                                                                                       |
| ClientSecret             | required | string  | The client secret that is being used for authenticating to Cds                                                                                                   |
| ApiVersion               | required | string  | The API version of the Cds endpoint                                                                                                                              |
| VerifySSL                | optional | boolean | A feature flag for verifying SSL when connecting to the Cds endpoint. By defualt this is set to true as it is strongly recommended that SSL be checked           |
| UseCompression           | optional | boolean | A feature flag for enabling compression on messages sent to the Cds endpoint                                                                                     |
| WebRequestTimeoutSeconds | optional | integer | A feature flag for changing how long it takes for a request to time out                                                                                          |

### EDS endpoint configurations

The format of the configuration for an EDS endpoint is shown below along with descriptions of each parameter. Replace all parameters with appropriate values.

```json
{
  "Selected": true,
  "EndpointType": "EDS",
  "Resource": "http://localhost:5590",
  "ApiVersion": "v1",
  "UseCompression": false
}
```

| Parameters               | Required | Type    | Description                                                                                                                                       |
| ------------------------ | -------- | ------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| Selected                 | required | boolean | Tells the application if the endpoint should be sent to                                                                                           |
| EndpointType             | required | string  | The endpoint type. For EDS this will always be "EDS"                                                                                              |
| Resource                 | required | string  | The endpoint for EDS if the namespace. If EDS is being run on your local machine with the default configuration, it will be http://localhost:5590 |
| ApiVersion               | required | string  | The API version of the EDS endpoint                                                                                                               |
| UseCompression           | optional | boolean | A feature flag for enabling compression on messages sent to the EDS endpoint                                                                      |
| WebRequestTimeoutSeconds | optional | integer | A feature flag for changing how long it takes for a request to time out                                                                           |

### PI endpoint configuration

The format of the configuration for a PI endpoint is shown below along with descriptions of each parameter. Replace all parameters with appropriate values.

```json
{
  "Selected": true,
  "EndpointType": "PI",
  "Resource": "PLACEHOLDER_REPLACE_WITH_PI_WEB_API_URL",
  "DataArchiveName": "PLACEHOLDER_REPLACE_WITH_DATA_ARCHIVE_NAME",
  "Username": "PLACEHOLDER_REPLACE_WITH_USERNAME",
  "Password": "PLACEHOLDER_REPLACE_WITH_PASSWORD",
  "VerifySSL": true,
  "UseCompression": false
}
```

| Parameters               | Required | Type           | Description                                                                                                                                                                                                                                                                             |
| ------------------------ | -------- | -------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Selected                 | required | boolean        | Tells the application if the endpoint should be sent to                                                                                                                                                                                                                                 |
| EndpointType             | required | string         | The endpoint type. For PI this will always be "PI"                                                                                                                                                                                                                                      |
| Resource                 | required | string         | The URL of the PI Web API                                                                                                                                                                                                                                                               |
| DataArchiveName          | required | string         | The name of the PI Data Archive that is being sent to                                                                                                                                                                                                                                   |
| Username                 | required | string         | The username that is being used for authenticating to the PI Web API                                                                                                                                                                                                                    |
| Password                 | required | string         | The password that is being used for authenticating to the PI Web API                                                                                                                                                                                                                    |
| VerifySSL                | optional | boolean/string | A feature flag for verifying SSL when connecting to the PI Web API. Alternatively, this can specify the path to a .pem certificate file if a self-signed certificate is being used by the PI Web API. By defualt this is set to true as it is strongly recommended that SSL be checked. |
| UseCompression           | optional | boolean        | A feature flag for enabling compression on messages sent to the PI endpoint                                                                                                                                                                                                            |
| WebRequestTimeoutSeconds | optional | integer        | A feature flag for changing how long it takes for a request to time out                                                                                                                                                                                                                 |

---

For the main OMF samples page [ReadMe](https://github.com/AVEVA/AVEVA-Samples-OMF)  
For the main AVEVA samples page [ReadMe](https://github.com/AVEVA)
