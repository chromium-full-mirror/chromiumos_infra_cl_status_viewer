This project is the backend server for ChromeOS-CL-Status-Viewer. Please find more context about ChromeOS-CL-Status-Viewer in the design document: go/chromeos-cl-status-viewer.

This project is currently running on Google Cloud Project chromeos-cl-viewer-api. It uses [Cloud Endpoints with OpenAPI](https://cloud.google.com/endpoints/docs/openapi/) to manage the APIs, runs the server on [App Engine Flexible Environment](https://cloud.google.com/appengine/docs/flexible/), and uses Python.


## Preparation

$PROJECT_ROOT = cl_status_viewer_server/

1. Download the CIDB credentials:
  Follow go/cros-cidb-admin and download prod_replica_cidb_gen2_readonly (or debug_cidb_gen2_readonly if necessary) credentials and put them under $PROJECT_ROOT/cidb_creds/prod_cidb_service.

2. Download the service account json file:
  a. Open the Credentials page of the API Manager in the [Cloud Console](https://console.cloud.google.com/apis/credentials).
  b. Click 'Create credentials'.
  c. Select 'Service account key'.
  d. In the 'Select service account' dropdown, select 'Create new service account'.
  e. Choose 'JSON' for the key type.
  f. rename it to chromeos-cl-viewer-api.json and put it under the path $PROJECT_ROOT/

## Running locally

1. Set up local environment for local CIDB connection, see instruction in ["Setting up your local environment" section](https://cloud.google.com/appengine/docs/flexible/python/using-cloud-sql).
  a. Install the Cloud SQL proxy.
  b. Create the Unix Sockets:
    i. Find <INSTANCE_CONNECTION_NAME> in [Instance details](https://pantheon.corp.google.com/sql/instances/cidb-gen2/overview?project=cosmic-strategy-646&organizationId=433637338589).
    ii. <PATH_TO_KEY_FILE> refers to chromeos-cl-viewer-api.json you downloaded before.
    e.g. If you downloaded the cidb-gen2-replica2 credentials, run command: ./cloud_sql_proxy -dir=/cloudsql -instances=cosmic-strategy-646:us-central1:cidb-gen2-replica2  -credential_file=chromeos-cl-viewer-api.json

2. Run the backend server locally.
  a. Install all the dependencies:
    ```bash
    virtualenv env
    source env/bin/activate
    pip install -r requirements.txt
    ```
  b. Compile the protocal buffers:
    ```bash
    protoc common/protos/viewer_message.proto  --python_out=.
    ```
  c. Run the application:
    ```bash
    python main.py
    ```

3. Try APIs with curl or a browser.
  a. http://localhost:$port/v1/index (e.g.http://127.0.0.1:8080/v1/index)
  b. http://localhost:$port/v1/internal_index (e.g.http://127.0.0.1:8080/v1/internal_index)
  c. http://localhost:$port/v1/gerrit/{gerrit}/changes/{change_id}/patches/{patch_number}/status
  (e.g. http://127.0.0.1:8080/v1/gerrit/chromium-review.googlesource.com/changes/764437/patches/9/status)


## Deploying to Production

1. Create an API key. With the project deployed to production, you'll need to create an API key to access the API.
  a. Open the Credentials page of the API Manager in the [Cloud Console](https://console.cloud.google.com/apis/credentials).
  b. Click 'Create credentials'.
  c. Select 'API Key'.
  d. Choose 'Server Key'
  e. Get the $APIKey

2. Deploy Endpoints and backend servers:
  a. Compile the protocal buffers:
    ```bash
    protoc common/protos/viewer_message.proto  --python_out=.
    ```
  b. deploy the app
    ```bash
    python deploy_app.py
    ```
    NOTE: This will replace the current Endpoints configuration and backend servers in chromeos-cl-viewer-api.

3. Try APIs with curl or a browser.
  a. https://chromeos-cl-viewer-api.appspot.com/v1/index
  b. https://chromeos-cl-viewer-api.appspot.com/v1/internal_index?key=$APIKey
  c. https://chromeos-cl-viewer-api.appspot.com/v1/gerrit/chromium-review.googlesource.com/changes/764437/patches/9/status?key=$APIKey
