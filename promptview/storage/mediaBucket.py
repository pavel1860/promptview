









import os
from components.image.image import Image
from components.storage.bucket import Bucket
from components.video.video import Video
from config import AWS_DATALAKE_BUCKET, TEMP_DIR
from components.media.media_file_util import video_extensions, image_extensions
from botocore.exceptions import ClientError

from datetime import datetime


class LakePath:

    PLATFORM_IDX = 0
    CHANNEL_IDX = 1
    DATE_IDX = 2
    FILE_IDX = -1

    def __init__(self, path):
        path_list = path.split('/')
        self.path = path
        self.platform = path_list[self.PLATFORM_IDX]
        self.channel = path_list[self.CHANNEL_IDX]
        self.date_str = path_list[self.DATE_IDX]
        self.partition = path_list[self.DATE_IDX]
        self.date = datetime.strptime(self.date_str, '%Y_%m_%d_%H_%M')
        self.file = path_list[self.FILE_IDX]

    def __repr__(self):
        return self.path
    
    def get_partition_key(self):
        return f"{self.platform}/{self.channel}/{self.date_str}"


class MediaBucket:

    def __init__(self) -> None:
        self.bucket = Bucket(AWS_DATALAKE_BUCKET)


    
    def list_files(self, filter=None):
        file_list = self.bucket.list_files()
        if filter is not None:
            if filter == "VIDEO":
                return [LakePath(path) for path in file_list if os.path.splitext(path)[1] in video_extensions]
            elif filter == "IMAGE":
                return [LakePath(path) for path in file_list if os.path.splitext(path)[1] in image_extensions]
        return [LakePath(path) for path in file_list]
    

    def iterate_files(self, postfix=None, continuation_token=None, max_keys=10):
        if postfix is None:
            files, continuation_token = self.bucket.iterate_files(
                continuation_token=continuation_token, 
                max_keys=max_keys
            )
            return [LakePath(path) for path in files], continuation_token
        file_list = []

        for _ in range(10):
            files, continuation_token = self.bucket.iterate_files(
                continuation_token=continuation_token, 
                max_keys=max_keys
            )
            file_list += [LakePath(path) for path in files if path.endswith(postfix)]
            if len(file_list) >= max_keys or len(files) < max_keys or continuation_token is None:
                break
        return file_list, continuation_token
    

    def list_partitions(self, platform, channel=None):
        prefix = f"{platform}/"
        if channel:
            prefix += f"{channel}/"
        file_list = self.bucket.list_folders(prefix)
        return [f.split('/')[-2] for f in file_list]
    
    def get_partition_json(self, platform, channel, date):
        prefix = f"{platform}/{channel}/{date}/"
        try:
            msgs = self.bucket.get_json(prefix + 'msgs.json')
            return msgs
        except ClientError as ex:
            if ex.response['Error']['Code'] == 'NoSuchKey':
                return None
            else:
                raise ex


    def list_partition_files(self, prefix):
        return self.bucket.list_files(prefix=prefix)          
    
    def add(self, data, key):
        self.bucket.add(data, key)

    def add_json(self, data, key):
        self.bucket.add_json(data, key)


    def get_json(self, key):
        return self.bucket.get_json(key)
    

    def get_media(self, platform, channel, date, filename):
        filename, ext = os.path.splitext(filename)
        # if ext in video_extensions:
            # return Video.from_stream(res, filename)
        file_path = f"{platform}/{channel}/{date}/{filename}{ext}"
        if ext in ['json']:
            return self.bucket.get_json(file_path)
        elif ext in image_extensions:
            obj = self.bucket.get(file_path)
            media = Image.from_bytes(obj.read())
        elif ext in video_extensions:
            obj = self.bucket.get_to_file(file_path, TEMP_DIR / f"{filename}{ext}")
            media.video = Video.from_file(TEMP_DIR / f"{filename}{ext}")

        return media

    async def aget_media(self, platform, channel, date, filename, metadata=None):
        filename, ext = os.path.splitext(filename)
        # if ext in video_extensions:
            # return Video.from_stream(res, filename)
        file_path = f"{platform}/{channel}/{date}/{filename}{ext}"
        if ext in ['json']:
            return await self.bucket.aget_json(file_path)
        elif ext in image_extensions:
            obj = await self.bucket.aget(file_path)
            media = Image.from_bytes(obj.read())
        elif ext in video_extensions:
            if metadata is None:
                raise Exception("metadata is not provided for video")
            obj = await self.bucket.aget_to_file(file_path, TEMP_DIR / f"{filename}{ext}")
            media = Video(
                filepath=TEMP_DIR / f"{filename}{ext}",
                width=metadata['width'],
                height=metadata['height'],
                duration=metadata['duration']                
            )
        return media
        