This project is the frontend server for ChromeOS-CL-Status-Viewer. Please find more context about ChromeOS-CL-Status-Viewer in the design document: go/chromeos-cl-status-viewer.

This project is currently running on Google Cloud Project google.com:chromeos-cl-viewer-ui. Please join mdb.chromeos-infra-app-owners@google.com group to be able to own the project. It runs on [App Engine Standard Environment](https://cloud.google.com/appengine/docs/standard/), and uses Python.

# Install virtualenv libraries (Required before local run or deployment to cloud)

From the directory where the app.yaml file is located, start the local development server with the following command:

pip install -r requirements.txt  -t ./lib

## Run and test locally

dev_appserver.py app.yaml

Visit http://localhost:8080/ in your web browser to view the app.

## Deploy your app to cloud

Run the following command from the directory where the app.yaml file is located:

1. Get API Key
  a. Open the Credentials page of the API Manager in the [Cloud Console](https://console.cloud.google.com/apis/credentials).
  b. Choose project 'google.com:chromeos-cl-viewer-ui'
  c. Click 'Create credentials'.
  d. Select 'API key'.
  e. Replace [REPLACE_WITH_API_KEY] in file chromeos-cl-viewer-ui-keys.json (NOTE: do not upload or checkin the API key file)

2. Run command
gcloud app deploy
