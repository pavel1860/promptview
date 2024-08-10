import json
import os
from pathlib import Path, PosixPath
import shutil
import boto3
import io
from components.image.image import Image
from components.video.video import Video
from components.audio.audio import Audio
from config import AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_SCRAPING_BUCKET, MOCK_BUCKET_FOLDER
from botocore.exceptions import ClientError
from botocore.client import Config
import asyncio



class BucketMock:

    def __init__(self, bucket_name: str, namespace: str, folder: str=MOCK_BUCKET_FOLDER) -> None:
        self.bucket_name = bucket_name
        self.namespace = namespace
        folder_path = Path(folder)        
        if not folder_path.exists():
            raise Exception("base folder is not existing")
        namespace_path = folder_path / namespace
        if not namespace_path.exists():
            os.mkdir(namespace_path)

        bucket_path = namespace_path / bucket_name
        if not bucket_path.exists():
            os.mkdir(bucket_path)
        self.bucket_path=bucket_path
        self.namespace_path = namespace_path

    def list_files(self, prefix=None):
        target_path = self.bucket_path 
        if prefix is not None:
            target_path = target_path / prefix
        file_list = []
        for root, dirs, files in os.walk(target_path):
            for file in files:
                rel_file = os.path.relpath(os.path.join(root, file), self.namespace_path)
                file_list.append(rel_file)
        return file_list
    

    def iterate_files(self, continuation_token=None, max_keys=10):
        raise NotImplementedError()
    

    def list_folders(self, prefix, delimiter="/"):    
        raise NotImplementedError()


    def add(self, data, key):
        keypath = self.bucket_path / Path(key)
        os.makedirs(str(keypath.parent), exist_ok=True)
        if str(type(data)) == str(Image):
            data = data.to_stream()
        elif str(type(data)) == str(Audio):
            data = data.to_io()
        elif str(type(data)) == str(Video):
            return self.add_file(data.filepath, key)
        with open(keypath, 'wb') as f:
            f.write(data.read())
        # return self.client.upload_fileobj(data, self.bucket_name, key, ExtraArgs={'ACL': 'bucket-owner-full-control'})

    def add_file(self, source_filepath: PosixPath, target_filename: str=None):
        target_filepath = self.bucket_path / target_filename
        os.makedirs(str(target_filepath.parent), exist_ok=True)
        try:
            target_filename = target_filename or source_filepath.name
            # res = self.client.upload_file(str(filepath), self.bucket_name, filename)
            # with open(self.bucket_path)
            shutil.copy(source_filepath, target_filepath)
            return None
        except ClientError as e:
            print(e)
            raise Exception('client error uploading file to s3')

    def remove(self, key):
        if (self.bucket_path / key).exists():
            (self.bucket_path / key).unlink()


    def remove_all(self):
        for item in os.listdir(self.bucket_path):
            item_path = self.bucket_path / item
            if os.path.isfile(item_path):
                os.unlink(item_path)
            else:
                shutil.rmtree(item_path)            

        
        # return self.client.delete_object(Bucket=self.bucket_name, Key=key)

    def get(self, key):
        with open(self.bucket_path / key, 'rb') as f:
            return f.read()
            # raw = io.BytesIO(f.read())
            # raw.seek(0)
            # return raw
        # obj = self.client.get_object(Bucket=self.bucket_name, Key=key)
    

    async def aget(self, key):
        raw = await asyncio.to_thread(
            # self.client.get_object,
            self.get,
            key=key
        )
        # raw = io.BytesIO(obj['Body'].read())
        # raw.seek(0)
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
        return json.loads(data.decode())
    
    async def aget_json(self, key):
        raise NotImplementedError()
        # data = await self.aget(key)
        # return json.loads(data.read().decode())
    

    def file_exists(self, key):       
        raise NotImplementedError()
        # try:
        #     self.client.head_object(Bucket=self.bucket_name, Key=key)
        #     return True
        # except ClientError as e:
        #     # If a client error is thrown, check if it was a 404 error (object not found)
        #     # If it was a 404 error, then the object does not exist.
        #     if e.response['Error']['Code'] == '404':
        #         return False
        #     else:
        #         # If it was some other kind of error, rethrow it
        #         raise
    

    def delete_bucket(self):
        if os.path.exists(self.bucket_path):
            shutil.rmtree(self.bucket_path)
            print(f"namespace '{self.bucket_name}' and all its contents have been deleted.")
        else:
            print(f"Folder '{self.bucket_name}' does not exist.")
