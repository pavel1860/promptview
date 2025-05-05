





# Artifact Model
artifact models are versioned event source models that give the ability to have revisions for the data and have version control over them.

```python
from enum import StrEnum
from uuid import UUID
from promptview.model import ArtifactModel, ModelField, Relation



class LikeType(StrEnum):
    LIKE = "like"
    DISLIKE = "dislike"


class Like(ArtifactModel):
    type: LikeType = ModelField()
    user_id: int = ModelField(foreign_key=True)
    post_id: UUID = ModelField(foreign_key=True)



class Post(ArtifactModel):
    title: str = ModelField()
    content: str = ModelField()
    owner_id: int = ModelField(foreign_key=True)
    likes: Relation[Like] = RelationField(foreign_key="post_id")

```