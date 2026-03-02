from azure.storage.blob import BlobServiceClient
import os

conn_str = os.environ["AZURE_STORAGE_CONNECTION_STRING"]
service = BlobServiceClient.from_connection_string(conn_str)

container = service.get_container_client("dreams")

data = b"hello world"

blob = container.get_blob_client("test/hello2.txt")
blob.upload_blob(data, overwrite=True)

print("Uploaded!")

