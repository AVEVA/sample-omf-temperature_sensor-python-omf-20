# NOTE: this script uses the v2.0 version of the OMF specification.
# Reference: https://docs.aveva.com/bundle/omf/page/1283983.html
# *************************************************************************************

# ************************************************************************
# Import necessary packages
# ************************************************************************
import enum
import json
import sys
import requests
import time
import datetime
import gzip
import random
import traceback
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

ERROR_STRING = 'Error'
TYPE_ID = 'Temperature.Float'
EVENT_TYPE_ID = 'Temperature.SL.Event'
CONTAINER_ID = 'Sample.Script.SL6658.Temperature'
EVENT_ID = 'Sample.Script.SL6658.TemperatureEvent'

# List of possible endpoint types
class EndpointTypes(enum.Enum):
    CDS = 'CDS'
    CONNECTEAP = 'CONNECTEAP'
    EDS = 'EDS'
    PI = 'PI'

# The version of the OMF messages
omf_version = '2.0'

def get_token(endpoint):
    '''Gets the token for the omfendpoint'''

    endpoint_type = endpoint["EndpointType"]
    # return an empty string for endpoints that don't use bearer tokens
    if endpoint_type not in (EndpointTypes.CDS, EndpointTypes.CONNECTEAP):
        return ''

    if (('expiration' in endpoint) and (endpoint["expiration"] - time.time()) > 5 * 60):
        return endpoint["token"]

    # CONNECTEAP provides the token URL directly in the endpoint config; no discovery needed.
    if endpoint_type == EndpointTypes.CONNECTEAP:
        token_url = urlparse(endpoint["TokenEndpoint"])
        # Validate URL
        assert token_url.scheme == 'https'

        token_information = requests.post(
            token_url.geturl(),
            data={'client_id': endpoint["ClientId"],
                  'client_secret': endpoint["ClientSecret"],
                  'grant_type': 'client_credentials'},
            verify=endpoint["VerifySSL"])
    else:
        # CDS uses OpenID Connect discovery to find the token endpoint.
        discovery_url = requests.get(
            endpoint["Resource"] + '/identity/.well-known/openid-configuration',
            headers={'Accept': 'application/json'},
            verify=endpoint["VerifySSL"])

        if discovery_url.status_code < 200 or discovery_url.status_code >= 300:
            discovery_url.close()
            raise Exception(f'Failed to get access token endpoint from discovery URL: {discovery_url.status_code}:{discovery_url.text}')

        token_endpoint = json.loads(discovery_url.content)["token_endpoint"]
        token_url = urlparse(token_endpoint)
        # Validate URL
        assert token_url.scheme == 'https'
        assert token_url.geturl().startswith(endpoint["Resource"])

        token_information = requests.post(
            token_url.geturl(),
            data={'client_id': endpoint["ClientId"],
                  'client_secret': endpoint["ClientSecret"],
                  'grant_type': 'client_credentials'},
            verify=endpoint["VerifySSL"])

    token = json.loads(token_information.content)

    if token is None:
        raise Exception('Failed to retrieve Token')

    __expiration = float(token["expires_in"]) + time.time()
    __token = token["access_token"]

    # cache the results
    endpoint["expiration"] = __expiration
    endpoint["token"] = __token

    return __token


def send_message_to_omf_endpoint(endpoint, message_type, message_omf_json, action='create'):
    '''Sends the request out to the preconfigured endpoint'''

    # Compress json omf payload, if specified
    compression = 'none'
    if endpoint["UseCompression"]:
        msg_body = gzip.compress(bytes(json.dumps(message_omf_json), 'utf-8'))
        compression = 'gzip'
    else:
        msg_body = json.dumps(message_omf_json)

    # Collect the message headers
    msg_headers = get_headers(endpoint, compression, message_type, action)

    # Send message to CDS endpoint
    endpoints_type = endpoint["EndpointType"]
    response = {}
    # If the endpoint is CDS or CONNECTEAP (both use bearer-token + HTTPS POST)
    if endpoints_type in (EndpointTypes.CDS, EndpointTypes.CONNECTEAP):
        response = requests.post(
            endpoint["OmfEndpoint"],
            headers=msg_headers,
            data=msg_body,
            verify=endpoint["VerifySSL"],
            timeout=endpoint["WebRequestTimeoutSeconds"]
        )
    # If the endpoint is EDS
    elif endpoints_type == EndpointTypes.EDS:
        response = requests.post(
            endpoint["OmfEndpoint"],
            headers=msg_headers,
            data=msg_body,
            timeout=endpoint["WebRequestTimeoutSeconds"]
        )
    # If the endpoint is PI
    elif endpoints_type == EndpointTypes.PI:
        response = requests.post(
            endpoint["OmfEndpoint"],
            headers=msg_headers,
            data=msg_body,
            verify=endpoint["VerifySSL"],
            timeout=endpoint["WebRequestTimeoutSeconds"],
            auth=(endpoint["Username"], endpoint["Password"])
        )

    # Check for 409, which indicates that a type with the specified ID and version already exists.
    if response.status_code == 409:
        if endpoint.get("PrintHttpResponses"):
            print(f'[HTTP] {message_type}/{action} -> {response.status_code} (already exists, ignored)')
        return

    # Optionally log every response (success and failure) for debugging.
    if endpoint.get("PrintHttpResponses"):
        body = response.text
        if len(body) > 1000:
            body = body[:1000] + f'... [truncated {len(response.text) - 1000} bytes]'
        print(f'[HTTP] {message_type}/{action} -> {response.status_code} {body}')

    # response code in 200s if the request was successful!
    if response.status_code < 200 or response.status_code >= 300:
        print(msg_headers)
        response.close()
        print(
            f'Response from relay was bad. {message_type} message: {response.status_code} {response.text}.  Message holdings: {message_omf_json}')
        print()
        raise Exception(f'OMF message was unsuccessful, {message_type}. {response.status_code}:{response.text}')


def get_headers(endpoint, compression='', message_type='', action=''):
    '''Assemble headers for sending to the endpoint's OMF endpoint'''

    endpoint_type = endpoint["EndpointType"]

    msg_headers = {
        'messagetype': message_type,
        'action': action,
        'messageformat': 'JSON',
        'omfversion': omf_version
    }

    if(compression == 'gzip'):
        msg_headers["compression"] = 'gzip'

    # If the endpoint is CDS or CONNECTEAP, attach the bearer token
    if endpoint_type in (EndpointTypes.CDS, EndpointTypes.CONNECTEAP):
        msg_headers["Authorization"] = f'Bearer {get_token(endpoint)}'
    # If the endpoint is PI
    elif endpoint_type == EndpointTypes.PI:
        msg_headers["x-requested-with"] = 'xmlhttprequest'

    # validate headers to prevent injection attacks
    validated_headers = {}

    for key in msg_headers:
        if key in {'Authorization', 'messagetype', 'action', 'messageformat', 'omfversion', 'x-requested-with', 'compression'}:
            validated_headers[key] = msg_headers[key]

    return validated_headers

def one_time_send_creates(endpoint):
    action = 'create'
    one_time_send_schema(endpoint, action)
    one_time_send_instances(endpoint, action)

def one_time_send_deletes(endpoint):
    print()
    print("Deleting sample data...")
    print()
    action = 'delete'
    try:
        one_time_send_instances(endpoint, action)
    except Exception as ex:
        print()
        # Ignore errors in deletes to ensure we clean up as much as possible
        print(("Error in deletes: {error}".format(error=ex)))
        print()

    try:
        one_time_send_schema(endpoint, action)
    except Exception as ex:
        print()
        # Ignore errors in deletes to ensure we clean up as much as possible
        print(("Error in deletes: {error}".format(error=ex)))
        print()


def one_time_send_schema(endpoint, action):
    # OMF 2.0 Schema message: defines types and containers in a single payload.
    # - classification "entity"        => static asset types
    # - classification "streamingdata" => time-series stream types (require an isindex property)
    # - isname is deprecated in OMF 2.0 and has been removed.
    send_message_to_omf_endpoint(endpoint, "schema", {
        "types": [
            {
                "id": "RemoteAssets.RootType",
                "name": "Root Asset Type",
                "classification": "entity",
                "type": "object",
                "description": "Root remote asset type",
                "properties": {
                    "Location": {
                        "type": "string",
                        "description": "Location of the asset"
                    }
                }
            },
            {
                "id": "RemoteAssets.FuelPumpType",
                "name": "Fuel Pump Asset Type",
                "classification": "entity",
                "type": "object",
                "description": "Remote pump asset type",
                "properties": {
                    "Location": {
                        "type": "string",
                        "description": "Location of the asset"
                    }
                }
            },
            {
                "id": TYPE_ID,
                "name": "Temperature Float Type",
                "classification": "streamingdata",
                "type": "object",
                "properties": {
                    "Timestamp": {
                        "format": "date-time",
                        "type": "string",
                        "isindex": True
                    },
                    "Temperature": {
                        "type": "number",
                        "description": "Temperature readings",
                        "uom": "degree Fahrenheit"
                    }
                }
            },
            {
                "id": EVENT_TYPE_ID,
                "name": "Temperature Event Type",
                "classification": "event",
                "baseTypeId": "BaseEvent",
                "type": "object",
                "properties": {
                    "Timestamp": {
                        "format": "date-time",
                        "type": "string",
                        "isindex": True
                    },
                    "EventMessage": {
                        "type": "string",
                        "description": "Description of the temperature event"
                    },
                    "Severity": {
                        "type": "string",
                        "description": "Severity level of the event (info, warning, error)"
                    }
                }
            }
        ],
        "Containers": [
            {
                "id": CONTAINER_ID,
                "name": "Temperature",
                "typeid": TYPE_ID,
                "description": "Container holds temperature measurements"
            }
        ]
    }, action)


def one_time_send_instances(endpoint, action):
    # OMF 2.0 Instance message: entities and relationships are sent together
    # in a single, strongly-typed payload. Static instances now use the
    # "entities" array with top-level id/name and a "value" object.
    # __Link is replaced by "relationships" with explicit source/target
    # "collection" values (entities, containers, events, types).
    send_message_to_omf_endpoint(endpoint, "instance", {
        "entities": [
            {
                "typeid": "RemoteAssets.RootType",
                "id": "RemoteAssets.Pumps.Root",
                "name": "Remote Fuel Pumps",
                "value": {}
            },
            {
                "typeid": "RemoteAssets.FuelPumpType",
                "id": "RemoteAssets.Pump.SL6658",
                "description": "SL6658 fuel pump asset",
                "name": "SL6658 Pump",
                "value": {
                    "Location": "SLTC, San Leandro, California"
                }
            }
        ],
        "relationships": [
            {
                "source": {
                    "collection": "entities",
                    "id": "RemoteAssets.Pumps.Root",
                    "type": "Parent",
                    "label": "Is Child of"
                },
                "target": {
                    "collection": "entities",
                    "id": "RemoteAssets.Pump.SL6658"
                }
            },
            {
                "source": {
                    "collection": "entities",
                    "id": "RemoteAssets.Pump.SL6658",
                    "type": "Parent",
                    "label": "Is Child of"
                },
                "target": {
                    "collection": "streamingdata",
                    "id": CONTAINER_ID
                }
            }
        ]
    }, action)


def create_data_value(value):
    """Creates an OMF 2.0 instance message carrying streaming data for the container."""
    return {
        "streamingdata": [
            {
                "id": CONTAINER_ID,
                "values": [
                    {
                        "Timestamp": get_current_time(),
                        "Temperature": value
                    }
                ]
            }
        ]
    }

def create_event_value(event_id, message, severity="info", starttime=None, endtime=None):
    """Creates an OMF 2.0 instance message carrying an event.

    Pass `endtime` to close a previously opened event. The same `event_id`
    and `starttime` must be reused so the endpoint updates the existing
    event rather than creating a new one.
    """
    if starttime is None:
        starttime = get_current_time()

    event = {
        "typeid": EVENT_TYPE_ID,
        "id": event_id,
        "datasource": "Temperature Sensor Script",
        "name": "Temperature Event",
        "starttime": starttime,
        "properties": {},
        "value": {
            "Timestamp": starttime,
            "EventMessage": message,
            "Severity": severity
        }
    }
    if endtime is not None:
        event["endtime"] = endtime

    return {
        "events": [event],
        "relationships": [
            {
                "source": {
                    "collection": "events",
                    "type": "Related",
                    "id": event_id,
                    "label": "Belongs to Entity"
                },
                "target": {
                    "collection": "entities",
                    "id": "RemoteAssets.Pump.SL6658"
                }
            },
            {
                "source": {
                    "collection": "events",
                    "type": "Related",
                    "id": event_id,
                    "label": "References Stream"
                },
                "target": {
                    "collection": "streamingdata",
                    "id": CONTAINER_ID
                }
            }
        ]
    }


def check_temperature_conditions(temperature):
    """
    Checks if the temperature meets any event conditions.
    Returns a tuple (condition_key, event_message, severity).
    condition_key is None when the temperature is in the normal range.

    Note: random values are 20.0 - 50.0 °F (random 200-500 / 10), so
    thresholds are tuned to that range to exercise open/close behavior.
    """
    temperature = float(temperature)

    # Trigger event if temperature is critically high (>45)
    if temperature > 45:
        return "critical_high", f"Critical: Temperature exceeds safe threshold: {temperature}°F", "error"

    # Trigger event if temperature is high (>40)
    elif temperature > 40:
        return "high", f"Warning: Temperature is elevated: {temperature}°F", "warning"

    # Trigger event if temperature is low (<25)
    elif temperature < 25:
        return "low", f"Warning: Temperature is below normal range: {temperature}°F", "warning"

    return None, None, None


def get_random_value():
    """Returns random integer value in 200 - 500 range"""
    value = random.randrange(200, 500)
    return str(value)


def get_current_time():
    """Returns the current time in UTC format"""
    # datetime.utcnow() is deprecated since Python 3.12; use a timezone-aware UTC value instead.
    return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f') + 'Z'


def get_json_file(filename):
    ''' Get a json file by the path specified relative to the application's path'''

    # Try to open the configuration file
    try:
        with open(
            filename,
            'r',
        ) as f:
            loaded_json = json.load(f)
    except Exception as error:
        print(f'Error: {str(error)}')
        print(f'Could not open/read file: {filename}')
        sys.exit(1)

    return loaded_json


def get_appsettings():
    ''' Return the appsettings.json as a json object, while also populating base_endpoint, omf_endpoint, and default values'''

    # Try to open the configuration file
    appsettings = get_json_file('appsettings.json')
    endpoints = appsettings["Endpoints"]

    # for each endpoint construct the check base and OMF endpoint and populate default values
    for endpoint in endpoints:
        if endpoint["EndpointType"] == 'OCS':
            print('OCS endpoint type is deprecated as OSIsoft Cloud Services has now been migrated to CONNECT data services, using CDS type instead.')
            endpoint_type = EndpointTypes.CDS
        else:
            endpoint["EndpointType"] = EndpointTypes(endpoint["EndpointType"])
            endpoint_type = endpoint["EndpointType"]

        # If the endpoint is CDS
        if endpoint_type == EndpointTypes.CDS:
            base_endpoint = f'{endpoint["Resource"]}/api/{endpoint["ApiVersion"]}' + \
                f'/tenants/{endpoint["TenantId"]}/namespaces/{endpoint["NamespaceId"]}'
            omf_endpoint = f'{base_endpoint}/omf'

        # If the endpoint is CONNECTEAP, the OMF endpoint URL is supplied directly in config
        # (no Resource/Tenant/Namespace path construction needed)
        elif endpoint_type == EndpointTypes.CONNECTEAP:
            omf_endpoint = endpoint.get("Endpoint")
            if not omf_endpoint:
                raise ValueError('CONNECTEAP endpoint requires an "Endpoint" value')
            if not endpoint.get("TokenEndpoint"):
                raise ValueError('CONNECTEAP endpoint requires a "TokenEndpoint" value')
            base_endpoint = omf_endpoint

        # If the endpoint is EDS
        elif endpoint_type == EndpointTypes.EDS:
            base_endpoint = f'{endpoint["Resource"]}/api/{endpoint["ApiVersion"]}' + \
                f'/tenants/default/namespaces/default'
            omf_endpoint = f'{base_endpoint}/omf'

        # If the endpoint is PI
        elif endpoint_type == EndpointTypes.PI:
            base_endpoint = endpoint["Resource"]
            omf_endpoint = f'{base_endpoint}/omf'

        else:
            raise ValueError('Invalid endpoint type')

        # add the base_endpoint and omf_endpoint to the endpoint configuration
        endpoint["BaseEndpoint"] = base_endpoint
        endpoint["OmfEndpoint"] = omf_endpoint

        # check for optional/nullable parameters
        if 'VerifySSL' not in endpoint or endpoint["VerifySSL"] == None:
            endpoint["VerifySSL"] = True

        if 'UseCompression' not in endpoint or endpoint["UseCompression"] == None:
            endpoint["UseCompression"] = True

        if 'WebRequestTimeoutSeconds' not in endpoint or endpoint["WebRequestTimeoutSeconds"] == None:
            endpoint["WebRequestTimeoutSeconds"] = 30

        # Per-endpoint toggle for verbose HTTP response logging. Falls back to the
        # top-level "PrintHttpResponses" appsettings flag if not set on the endpoint.
        if 'PrintHttpResponses' not in endpoint or endpoint["PrintHttpResponses"] is None:
            endpoint["PrintHttpResponses"] = bool(appsettings.get('PrintHttpResponses', False))

    return appsettings


def main(test=False):
    try:
        print('------------------------------------------------------------------')
        print(' .d88888b.  888b     d888 8888888888        8888888b. Y88b   d88P ')
        print('d88P" "Y88b 8888b   d8888 888               888   Y88b Y88b d88P  ')
        print('888     888 88888b.d88888 888               888    888  Y88o88P   ')
        print('888     888 888Y88888P888 8888888           888   d88P   Y888P    ')
        print('888     888 888 Y888P 888 888               8888888P"     888     ')
        print('888     888 888  Y8P  888 888               888           888     ')
        print('Y88b. .d88P 888   "   888 888               888           888     ')
        print(' "Y88888P"  888       888 888      88888888 888           888     ')
        print('------------------------------------------------------------------')

        # Configuration
        appsettings = get_appsettings()
        endpoints = appsettings.get('Endpoints')

        # Scanning configuration
        iterationCount = (int)(
            appsettings.get('NumberOfIterations'))
        delayBetweenRequests = (int)(
            appsettings.get('DelayBetweenRequests'))

        for endpoint in endpoints:
            if not endpoint["Selected"]:
                continue
            if endpoint["EndpointType"] in ["CDS","EDS","PI"]:
                print(f"Endpoint type {endpoint["EndpointType"]} not yet supported for OMF 2.X. Use OMF 1.X samples instead. Skipping endpoint.")
                continue

            one_time_send_creates(endpoint)

            count = 0
            # Tracks the currently-open event so we can close it (with an endtime)
            # when the temperature condition changes. Each new event gets a unique id.
            open_event = None  # dict with keys: id, condition, message, severity, starttime
            time.sleep(1)
            while count == 0 or ((not test) and count < iterationCount):
                # Use get_random_value() method to
                # generate random value for demonstration purposes.
                measurement = get_random_value()

                if(measurement == ERROR_STRING):
                    print('Unable to get data...')
                else:
                    value = int(measurement)/10
                    print("Sending value: ", value)
                    message = create_data_value(value)
                    send_message_to_omf_endpoint(endpoint, 'instance', message)

                    # Check temperature conditions and manage event lifecycle.
                    # An event remains open while the same condition persists. When the
                    # condition changes (or returns to normal), the open event is closed
                    # by sending an update that adds an `endtime`.
                    condition, event_message, severity = check_temperature_conditions(value)

                    if open_event is not None and condition != open_event["condition"]:
                        # Condition changed -> close the open event with an endtime.
                        close_time = get_current_time()
                        print(f"Event closed: {open_event['message']} (endtime={close_time})")
                        close_data = create_event_value(
                            open_event["id"],
                            open_event["message"],
                            open_event["severity"],
                            starttime=open_event["starttime"],
                            endtime=close_time
                        )
                        send_message_to_omf_endpoint(endpoint, 'instance', close_data, 'update')
                        open_event = None

                    if condition is not None and open_event is None:
                        # Open a new event with a unique id for this occurrence.
                        starttime = get_current_time()
                        new_event_id = f"{EVENT_ID}.{int(time.time() * 1000)}"
                        print(f"Event opened: {event_message}")
                        event_data = create_event_value(
                            new_event_id,
                            event_message,
                            severity,
                            starttime=starttime
                        )
                        send_message_to_omf_endpoint(endpoint, 'instance', event_data, 'create')
                        open_event = {
                            "id": new_event_id,
                            "condition": condition,
                            "message": event_message,
                            "severity": severity,
                            "starttime": starttime
                        }

                time.sleep(delayBetweenRequests)
                count = count + 1

            if (test):
                one_time_send_deletes(endpoint)

        print('Complete!')
        return True

    except Exception as ex:
        print()
        msg = 'Encountered Error: {error}'.format(error=ex)
        print(msg)
        print()
        traceback.print_exc()
        print()
        if (test):
            # Best-effort cleanup for any endpoints that completed creates before the failure.
            try:
                appsettings = locals().get('appsettings')
                if appsettings:
                    for endpoint in appsettings.get('Endpoints', []):
                        if endpoint.get('Selected') and 'OmfEndpoint' in endpoint:
                            try:
                                one_time_send_deletes(endpoint)
                            except Exception:
                                pass
            except Exception:
                pass
        assert False, msg


if __name__ == "__main__":
    main()
