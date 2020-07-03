import requests
import json
import datetime
import base64
import hashlib
import hmac
import os
from azure.storage.blob import BlobServiceClient, BlobClient, ContainerClient

def main():
    queries = get_queries()
    for query in queries:
        process_query(query)

# Process query
def process_query(query):
    logs = read_elastic(os.getenv('ELASTIC_URL'), query["data"])
    print("Sending data to Azure to {} table".format(query["table"]))
    post_data(os.getenv('WORKSPACE_ID'), os.getenv('WORKSPACE_KEY'), json.dumps(logs), query["table"])

# Read from Elastic
def read_elastic(url, data):
    headers = {'Content-Type': 'application/json'}
    print("Calling Elastic at {}".format(url))
    print(data)
    r = requests.post(url+"?size=10000", data=data, headers=headers)
    logs = []
    for record in json.loads(r.text)["hits"]["hits"]:
        logs.append(record["_source"])
    print("Parsed {} messages".format(len(logs)))
    return logs

# Get queries
def get_queries():
    blob_service_client = BlobServiceClient.from_connection_string(os.getenv('AZURE_STORAGE_CONNECTION_STRING'))
    container_client = blob_service_client.get_container_client(os.getenv('QUERIES_CONTAINER'))
    blob_list = container_client.list_blobs()
    queries = []
    for blob in blob_list:
        print(blob.name)
        blob_client = blob_service_client.get_blob_client(container=os.getenv('QUERIES_CONTAINER'), blob=blob.name)
        data = blob_client.download_blob().readall()
        query = {"table" : blob.name.split(".")[0], "data" : data}
        queries.append(query)
    return queries


# Function - Build the API signature
def build_signature(workspace_id, shared_key, date, content_length, method, content_type, resource):
  x_headers = 'x-ms-date:' + date
  string_to_hash = method + "\n" + str(content_length) + "\n" + content_type + "\n" + x_headers + "\n" + resource
  bytes_to_hash = str.encode(string_to_hash,'utf-8')  
  decoded_key = base64.b64decode(shared_key)
  encoded_hash = (base64.b64encode(hmac.new(decoded_key, bytes_to_hash, digestmod=hashlib.sha256).digest())).decode()
  authorization = "SharedKey {}:{}".format(workspace_id,encoded_hash)
  return authorization

# Function - Build and send a request to the POST API
def post_data(workspace_id, shared_key, body, log_type):
  method = 'POST'
  content_type = 'application/json'
  resource = '/api/logs'
  rfc1123date = datetime.datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S GMT')
  content_length = len(body)
  signature = build_signature(workspace_id, shared_key, rfc1123date, content_length, method, content_type, resource)
  uri = 'https://' + workspace_id + '.ods.opinsights.azure.com' + resource + '?api-version=2016-04-01'

  headers = {
      'content-type': content_type,
      'Authorization': signature,
      'Log-Type': log_type,
      'x-ms-date': rfc1123date,
      'time-generated-field': 'utc_time'
  }

  response = requests.post(uri,data=body, headers=headers)
  if (response.status_code >= 200 and response.status_code <= 299):
      print ('Accepted')
  else:
      print ("Response code: {}".format(response.status_code))

if __name__ == "__main__":
    main()