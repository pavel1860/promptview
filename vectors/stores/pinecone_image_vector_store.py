import asyncio
from typing import Any, List, Optional, Type, Union
import pinecone
from pinecone import Pinecone

from pydantic import BaseModel, Field
from components.image.llava_client import ImageToTextServerException, LlavaClient
from config import PINECONE_KEY, PINECONE_ENV

from components.image.image import Image
from uuid import uuid4
import numpy as np

# try:
#     from components.image.clip import Image2TextCLIP
# except:
#     pass

index_name = "images"



# pinecone.init(
#     api_key= PINECONE_KEY,
#     environment=PINECONE_ENV
# )


class PineconeVectorStoreException(Exception):
    pass



class ImageVectorRec(BaseModel):
    id: str
    backend_id: str
    embeddings: Optional[List[float]] = None
    score: float
    metadata: Optional[Any] = None


class PineconeImageVectorStore:

    index: pinecone.Index
    namespace: Union[str, None] 


    def __init__(self, index_name, namespace, init_ai=True, metadata_model: Type[BaseModel]=None) -> None:
        # self.embedding = Image2TextCLIP() if local==True else LlavaClient()
        try:
            self._embedding = LlavaClient() if init_ai==True else None
        except ImageToTextServerException as e:
            print('Failed to initialize AI. AI will not be available.')
            self._embedding = None
        self.pc = Pinecone(api_key=PINECONE_KEY)
        self.index_name = index_name
        self.index = self.pc.Index(index_name)
        self.namespace = namespace
        self.metadata_model = metadata_model


    @property
    def embedding(self):
        if self._embedding is None:
            raise PineconeVectorStoreException("Vision is not initialized. can't get embeddings.")
        return self._embedding
    
    def init_client(self):
        self.embedding = LlavaClient()


    def validate_metadata_model(self, metadata):
        if self.metadata_model:
            if type(metadata) == dict:
                return self.metadata_model(**metadata).dict()
            elif type(metadata) == self.metadata_model:
                return metadata.dict()
        return metadata


    def add_image(
            self, 
            image: Image, 
            metadata, 
            namespace=None, 
            backend_id=None, 
            image_embeddings: np.ndarray=None, 
            verify_duplicate=True, 
            duplicate_threshold=0.99,
            image_id=None,
        ):
        
        metadata = self.validate_metadata_model(metadata)
        if image_embeddings is None:
            image_embeddings = self.embedding.get_image_embeddings(image)
        namespace = namespace or self.namespace        
        # if image_id is None:
        # image_id = str(uuid4())
        metadata['backend_id'] = backend_id
        vector = (image_id, image_embeddings.tolist()[0], metadata)
        res = self.index.upsert(vectors=[vector], namespace=namespace)
        res['id'] = image_id
        res['embeddings'] = image_embeddings.tolist()[0]
        return res
    
    def get_image_raw(self, image_id, include_metadata=True):
        res = self.index.query(
            id=image_id, 
            top_k=1, 
            namespace=self.namespace,
            include_metadata=include_metadata
        )
        return res
    
    async def get_image(self, image_id, include_metadata=True):
        # res = await asyncio.to_thread(self.index.query,
        #     id=image_id, 
        #     top_k=1, 
        #     namespace=self.namespace,
        #     include_metadata=include_metadata
        # )
        vector = [0 for i in range(self.dimension)]
        res = await asyncio.to_thread(self.index.query,
            # id=image_id,
            vector=vector,
            top_k=1, 
            namespace=self.namespace,
            include_metadata=include_metadata,
            filter= { 
                "backend_id": {"$eq": image_id},
            }
        )
        if len(res.matches) == 0:
            return None
        match = res.matches[0]
        if self.metadata_model:
            metadata = self.metadata_model(**match.metadata)
        else:
            metadata = match.metadata
        vi = ImageVectorRec(
            id=match.id,
            backend_id=match.metadata['backend_id'],
            score=match.score,
            metadata=metadata
        )
        return vi
        

    # def add_image_embedding(self, image_embedding: np.ndarray, metadata, namespace=None, image_id=None):
    #     namespace = namespace or self.namespace        
    #     if image_id is None:
    #         image_id = str(uuid4())
    #     vector = (image_id, image_embedding.tolist()[0], metadata)
    #     res = self.index.upsert(vectors=[vector], namespace=namespace)
    #     res['id'] = image_id
    #     res['embeddings'] = image_embedding.tolist()[0]
    #     return res
    

    def get_image_embeddings(self, image: Image, namespace=None, verify_duplicate=True, duplicate_threshold=0.99):
        namespace = namespace or self.namespace        
        image_embedding = self.embedding.get_image_embeddings(image)
        # if verify_duplicate:
        #     similar_images = self.embedding_similarity_search(image_embedding, top_k=1, namespace=namespace)
        #     if len(similar_images) > 0 and similar_images[0].score > duplicate_threshold:
        #         return None
        return image_embedding
    

    async def aget_image_embeddings(self, image: Image, namespace=None):
        namespace = namespace or self.namespace        
        image_embedding = await self.embedding.aget_image_embeddings(image)
        # if verify_duplicate:
        #     similar_images = self.embedding_similarity_search(image_embedding, top_k=1, namespace=namespace)
        #     if len(similar_images) > 0 and similar_images[0].score > duplicate_threshold:
        #         return None
        return image_embedding
    
    
    async def aget_similar_image(self, image_embedding, duplicate_threshold=0.99, namespace=None):
        namespace = namespace or self.namespace
        similar_images = self.embedding_similarity_search(image_embedding, top_k=1, namespace=namespace)
        if len(similar_images) > 0 and similar_images[0].score > duplicate_threshold:
            return similar_images[0]
        return None


    @property
    def dimension(self):
        return self.index.describe_index_stats()['dimension']
    

    @property
    def total_vector_count(self):
        return self.index.describe_index_stats()['total_vector_count']    

    @property
    def namespaces(self):
        return self.index.describe_index_stats()['namespaces']
        
    @property
    def index_fullness(self):
        return self.index.describe_index_stats()['index_fullness']


    def text_similarity_search(self, text: str, filter=None, top_k=10, namespace=None, include_metadata=True):
        namespace = namespace or self.namespace
        vector = self.embedding.get_text_embeddings(text)
        return self.index.query(
            vector=vector.tolist()[0],
            filter=filter,
            top_k=top_k,
            namespace=namespace,
            include_metadata=include_metadata
        ).matches
    
    async def atext_similarity_search(self, text: str, filter=None, top_k=10, namespace=None, include_metadata=True, return_dict=False) -> List[ImageVectorRec]:
        namespace = namespace or self.namespace
        vector = await self.embedding.aget_text_embeddings(text)
        res = self.index.query(
            vector=vector.tolist()[0],
            filter=filter,
            top_k=top_k,
            namespace=namespace,
            include_metadata=include_metadata
        )
        matches = res.matches
        return [ImageVectorRec(
            id=m.id, 
            backend_id=m.metadata['backend_id'],
            score=m.score, 
            metadata=self.metadata_model(**m.metadata)) 
        for m in matches]
        # return [ImageVectorRec(id=m.id, score=m.score, metadata=m.metadata) for m in matches]
            # matches = [self.metadata_model(**m.metadata) for m in matches]
        # return matches

    def embedding_similarity_search(self, vector: np.ndarray, filter=None, top_k=10, namespace=None, include_metadata=True):
        namespace = namespace or self.namespace
        return self.index.query(
            vector=vector.tolist()[0],
            filter=filter,
            top_k=top_k,
            namespace=namespace,
            include_metadata=include_metadata
        ).matches
    
    
    def embedding_similarity_search(self, vector: np.ndarray, filter=None, top_k=10, namespace=None, include_metadata=True):
        namespace = namespace or self.namespace
        return self.index.query(
            vector=vector.tolist()[0],
            filter=filter,
            top_k=top_k,
            namespace=namespace,
            include_metadata=include_metadata
        ).matches
    

    def image_similarity_search(self, image: Image, filter=None, top_k=10, namespace=None, include_metadata=True):
        namespace = namespace or self.namespace
        vector = self.embedding.get_image_embeddings(image)
        return self.index.query(
            vector=vector.tolist()[0],
            filter=filter,
            top_k=top_k,
            namespace=namespace,
            include_metadata=include_metadata
        ).matches


    def get_many(self, top_k=100, namespace=None, filter=None, include_metadata=True):
        namespace = namespace or self.namespace
        # vector = self.embedding.get_text_embeddings("test vector")
        vector = [0 for i in range(self.dimension)]
        records = self.index.query(
            # vector=vector.tolist()[0],
            vector=vector,
            filter=filter,
            top_k=top_k,
            namespace=namespace,
            include_metadata=include_metadata
        )
        return records.matches
    

    def update(self, id: str, metadata: Any, namespace=None):
        namespace = namespace or self.namespace
        update_res = self.index.update(id, set_metadata=metadata, namespace=namespace )
        return update_res


    def delete(self, ids: Union[str, List[str]]=None, filter=None, delete_all=None, namespace=None):
        namespace = namespace or self.namespace
        if type(ids) == str:
            ids = [ids]
        return self.index.delete(
            ids, 
            filter=filter,
            delete_all=delete_all,
            namespace=namespace
        )

    @staticmethod
    def create_index(index_name, dimension, metric="dotproduct", pod_type="s1"):
        pinecone.create_index(
            index_name,
            dimension=dimension,
            metric=metric,
            pod_type=pod_type
        )

    @staticmethod
    def delete_index(index_name):
        pinecone.delete_index(index_name)