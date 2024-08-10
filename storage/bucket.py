import json
from pathlib import PosixPath
import boto3
import io
from chatboard.media.image.image import Image
from chatboard.media.video.video import Video
from chatboard.media.audio.audio import Audio
# from config import AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_SCRAPING_BUCKET
from botocore.exceptions import ClientError
from botocore.client import Config
import asyncio
import os

AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY")
class Bucket:

    def __init__(self, bucket_name: str) -> None:
        self.bucket_name = bucket_name
        self.client = boto3.client(
            's3',
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            config=Config(
                region_name = 'eu-west-2',
                signature_version='s3v4'
                )
        )

    def list_files(self, prefix=None):
        # objects = self.client.list_objects_v2(Bucket=self.bucket_name, Prefix=prefix)['Contents']
        res = self.client.list_objects_v2(Bucket=self.bucket_name)
        objects = res['Contents']
        sorted_objects = reversed(sorted(objects, key= lambda x: x['LastModified']))
        return [f.get('Key') for f in sorted_objects]
    

    def iterate_files(self, continuation_token=None, max_keys=10):
        if continuation_token is None:
            res = self.client.list_objects_v2(Bucket=self.bucket_name, MaxKeys=max_keys)
        else:
            res = self.client.list_objects_v2(Bucket=self.bucket_name, ContinuationToken=continuation_token, MaxKeys=max_keys)
        objects = res['Contents']
        next_continuation_token = res.get('NextContinuationToken')
        sorted_objects = reversed(sorted(objects, key= lambda x: x['LastModified']))
        return [f.get('Key') for f in sorted_objects], next_continuation_token
    

    def list_folders(self, prefix, delimiter="/"):    
        response = self.client.list_objects_v2(Bucket=self.bucket_name, Prefix=prefix, Delimiter=delimiter)
        folders = []
        if 'CommonPrefixes' in response:
            for entry in response['CommonPrefixes']:
                folders.append(entry['Prefix'])
        return folders


    def add(self, data, key):
        if type(data) == Image:
            data = data.to_stream()
        elif type(data) == Audio:
            data = data.to_io()
        elif type(data) == Video:
            return self.add_file(data.filepath, key)
        return self.client.upload_fileobj(data, self.bucket_name, key, ExtraArgs={'ACL': 'bucket-owner-full-control'})

    def add_file(self, filepath: PosixPath, filename: str=None):
        try:
            filename = filename or filepath.name
            res = self.client.upload_file(str(filepath), self.bucket_name, filename)
            return res
        except ClientError as e:
            print(e)
            raise Exception('client error uploading file to s3')

    def remove(self, key):
        return self.client.delete_object(Bucket=self.bucket_name, Key=key)

    def get(self, key):
        obj = self.client.get_object(Bucket=self.bucket_name, Key=key)
        raw = io.BytesIO(obj['Body'].read())
        raw.seek(0)
        return raw
    

    async def aget(self, key):
        obj = await asyncio.to_thread(
            self.client.get_object,
            Bucket=self.bucket_name, 
            Key=key
        )
        raw = io.BytesIO(obj['Body'].read())
        raw.seek(0)
        return raw
    
    def get_to_file(self, key, filepath):
        self.client.download_file(self.bucket_name, key, str(filepath))

    async def aget_to_file(self, key, filepath):
        res = await asyncio.to_thread(
            self.client.download_file,
            self.bucket_name,
            key,
            str(filepath)    
        ) 
        return res

    def add_json(self, data, key):
        buf = io.BytesIO()
        buf.write(json.dumps(data).encode())
        buf.seek(0)
        return self.add(buf, key)
    
    def get_json(self, key):
        data = self.get(key)
        return json.loads(data.read().decode())
    
    async def aget_json(self, key):
        data = await self.aget(key)
        return json.loads(data.read().decode())
    

    def file_exists(self, key):       
        try:
            self.client.head_object(Bucket=self.bucket_name, Key=key)
            return True
        except ClientError as e:
            # If a client error is thrown, check if it was a 404 error (object not found)
            # If it was a 404 error, then the object does not exist.
            if e.response['Error']['Code'] == '404':
                return False
            else:
                # If it was some other kind of error, rethrow it
                raise