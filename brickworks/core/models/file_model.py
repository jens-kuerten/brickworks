import uuid

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from brickworks.core.exceptions import NotFoundException
from brickworks.core.models.base_dbmodel import UUID_LENGTH, BaseDBModel
from brickworks.core.module_loader import get_models_by_fqpn

PUBLIC_BLOB_ID_PREFIX = "public-"


class WithFilesMixin(BaseDBModel):
    __abstract__ = True

    async def on_file_created(self, file_record: "FileModel") -> None:
        """
        This method is called after a file is created. At this stage only the file record is
        created, but no file is uploaded yet.
        You can still raise an exception here, which will rollback the transaction and thus
        prevent the file from being created.
        """
        pass


class FileModel(BaseDBModel):
    __tablename__ = "core_files"
    blob_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    parent_uuid: Mapped[str] = mapped_column(String(UUID_LENGTH), nullable=False)
    parent_fqpn: Mapped[str] = mapped_column(String(255), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    mimetype: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    finalized: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    @classmethod
    async def create(
        cls,
        user_uuid: str,
        file_name: str,
        parent_uuid: str,
        parent_fqpn: str,
        size: int = 0,
        mimetype: str | None = None,
        public: bool = False,
    ) -> "FileModel":
        """
        Create a new file record in the database.
        Files need to be attached to a parent object, which is identified by the parent_uuid and
        the fully qualified path name of the parent object.

        By default, blobs are not public, meaning a presigned URL is required to access them.
        Public blobs can be accessed directly through a static URL.
        This is useful for files that are meant to be shared publicly, such as images on a website.
        """
        parent_object_class = get_models_by_fqpn().get(parent_fqpn)
        if not parent_object_class:
            raise ValueError(f"Parent object class not found for fqpn: {parent_fqpn}")
        # check that the parent class is a subclass of WithFilesMixin
        if not issubclass(parent_object_class, WithFilesMixin):
            raise ValueError(f"Parent object class {parent_fqpn} is not a subclass of WithFilesMixin")

        # check that the parent object exists
        parent_object = await parent_object_class.get_one_or_none(uuid=parent_uuid)
        if not parent_object:
            raise NotFoundException(f"Parent object with UUID {parent_uuid} of class {parent_fqpn} not found")

        file_record = await cls(
            blob_id=cls.generate_blob_id(public=public),
            file_name=file_name,
            parent_uuid=parent_uuid,
            parent_fqpn=parent_fqpn,
            size=size,
            mimetype=mimetype,
        ).persist()
        await parent_object.on_file_created(file_record)
        return file_record

    @staticmethod
    def generate_blob_id(public: bool = False) -> str:
        """
        Generate a unique blob ID for the file.
        This is a placeholder implementation. In a real application, you would use a more robust
        method to generate unique IDs, such as UUIDs or a combination of timestamp and random
        string.
        """

        blob_id = str(uuid.uuid4())
        if public:
            blob_id = PUBLIC_BLOB_ID_PREFIX + blob_id
        return blob_id
