This project is the frontend server for ChromeOS-CL-Status-Viewer. Please find more context about ChromeOS-CL-Status-Viewer in the design document: go/chromeos-cl-status-viewer.

This project is currently running on Google Cloud Project google.com:chromeos-cl-viewer-ui. Please join mdb.chromeos-infra-app-owners@google.com group to be able to own the project. It runs on [App Engine Standard Environment](https://cloud.google.com/appengine/docs/standard/), and uses Python.

## Run locally

From the directory where the app.yaml file is located, start the local development server with the following command:

pip install -r requirements.txt  -t ./lib

dev_appserver.py app.yaml

Visit http://localhost:8080/ in your web browser to view the app.

## Deploy your app

Run the following command from the directory where the app.yaml file is located:

gcloud app deploy
