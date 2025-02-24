import pymongo
from bson import ObjectId
from pydantic import BaseModel, ValidationError
from pymongo import ReturnDocument
from pymongo.collection import Collection
from typing import Generic, List, Type, TypeVar, Union

from . import database_models


M = TypeVar('M', bound=database_models.DatabaseEntry)


def _jsonify_oid(obj: Union[dict, ObjectId, None]):
    if obj is None:
        return None
    elif isinstance(obj, ObjectId):
        return obj.binary.hex()
    else:
        oid: ObjectId = obj.pop("_id", None)
        if oid is not None:
            obj["id"] = oid.binary.hex()
        return obj


def _prepare_filter(obj: Union[dict, str, None]):
    if obj is None:
        return {}

    elif isinstance(obj, str):
        return {"_id": ObjectId(obj)}

    else:
        id = obj.pop("id", None)
        if id is not None:
            obj["_id"] = ObjectId(id)
        return obj


class DocumentCollection(Generic[M]):
    def __init__(self, collection: Collection, model: Type[M]):
        self.collection = collection
        self.model = model
        self.name = collection.name
        self.collection.create_index("name")

    def create(self, obj: M) -> M:
        obj.id = self.insert_one(obj.model_dump())
        return obj

    def save(self, obj: M):
        if not obj.id:
            obj.id = ObjectId().binary.hex()
        self.upsert(obj.id, obj.model_dump("json"))

    def pre_process_filter(self, filter: Union[dict, str, None, M]):
        if isinstance(filter, BaseModel):
            return _prepare_filter(filter.model_dump(mode="json"))
        else:
            return _prepare_filter(filter)

    def post_process_result(self, document: dict) -> M:
        if document is None:
            return None

        try:
            return self.model.model_validate(_jsonify_oid(document))
        except ValidationError as exc:
            for error in exc.errors():
                location = list(error['loc'])
                terminal = location.pop()

                ancestry: list[tuple[dict|list, str|int]] = []
                cursor = document
                for component in location:
                    ancestry.append((cursor, component))
                    cursor = cursor[component]

                if isinstance(cursor, list):
                    cursor.pop(terminal)
                elif isinstance(cursor, set):
                    cursor.discard(error['input'])
                else:
                    del cursor[terminal]

            return self.model.model_validate(_jsonify_oid(document))


    def create_index(self, *args, **kwargs):
        self.collection.create_index(*args, **kwargs)

    def find_one(self, filter: Union[dict, str, M, None]) -> M:
        if filter is None:
            return None
        return self.post_process_result(self.collection.find_one(self.pre_process_filter(filter)))

    def find(self, filter: Union[dict, str, M, None] = None, *args, **kwargs) -> List[M]:
        return [self.post_process_result(document) for document in self.collection.find(self.pre_process_filter(filter), *args, **kwargs)]

    def delete_one(self, filter: Union[dict, str, M, None] = None, *args, **kwargs):
        return self.collection.delete_one(self.pre_process_filter(filter), *args, **kwargs).deleted_count != 0

    def delete_many(self, filter: Union[dict, str, M, None] = None, *args, **kwargs):
        return self.collection.delete_many(self.pre_process_filter(filter), *args, **kwargs).deleted_count

    def find_one_and_update(self, filter: Union[dict, str, M, None], update: dict, *args, **kwargs) -> M:
        if filter is None:
            return None
        return self.post_process_result(
            self.collection.find_one_and_update(
                self.pre_process_filter(filter),
                update,
                *args,
                return_document=ReturnDocument.AFTER,
                **kwargs
            )
        )

    def update_many(self, filter: Union[dict, str, M, None], update: dict, *args, **kwargs) -> int:
        return self.collection.update_many(self.pre_process_filter(filter), update, *args, **kwargs).matched_count

    def upsert(self, filter: Union[dict, str, M, None], update: dict, *args, **kwargs):
        return _jsonify_oid(self.collection.update_one(self.pre_process_filter(filter), update, *args, **kwargs, upsert=True).upserted_id)

    def insert_one(self, *args, **kwargs) -> str:
        return _jsonify_oid(self.collection.insert_one(*args, **kwargs).inserted_id)

    def insert_many(self, *args, **kwargs) -> List[str]:
        return [_jsonify_oid(id) for id in self.collection.insert_many(*args, **kwargs).inserted_ids]


# Mongo Client
client = pymongo.MongoClient("mongodb://archon_db:27017")
db = client.archon_db

# Collections
users = DocumentCollection(db.users, database_models.User)
channels = DocumentCollection(db.channels, database_models.Channel)
