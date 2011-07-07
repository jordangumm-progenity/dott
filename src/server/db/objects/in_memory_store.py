import couchdb
from couchdb.http import ResourceNotFound

from settings import DATABASES
from src.utils import logger
from src.server.parent_loader import PARENT_LOADER

class InMemoryObjectStore(object):
    """
    Serves as an in-memory object store for all "physical" entities in the
    game. An "object" can be stuff like a room or a thing.
    """
    def __init__(self, db_name=None):
        """
        :param str db_name: Overrides the DB name for the object DB.
        """
        # Reference to CouchDB server connection.
        self._server = couchdb.Server()
        # Eventually contains a CouchDB reference. Queries come through here.
        self._db = None
        # Loads or creates+loads the CouchDB database.
        self._prep_db(db_name=db_name)
        # Keys are CouchDB ids, values are the parent instances (children of
        # src.game.parents.base_objects.base.BaseObject
        self._objects = {}
        # Loads all of the objects into RAM from CouchDB.
        self._load_objects_into_ram()

    def _prep_db(self, db_name=None):
        """
        Sets the :attr:`_db` reference. Creates the CouchDB if the requested
        one doesn't exist already.

        :param str db_name: Overrides the DB name for the object DB.
        """
        if not db_name:
            # Use the default configured DB name for objects DB.
            db_name = DATABASES['objects']['NAME']

        try:
            # Try to get a reference to the CouchDB database.
            self._db = self._server[db_name]
        except ResourceNotFound:
            logger.warning('No DB found, creating a new one.')
            self._db = self._server.create(db_name)

        if not len(self._db):
            # No objects are in this DB. We know the starter room can't
            # exist yet, so create it.
            self._create_initial_room()

    def _load_objects_into_ram(self):
        """
        Loads all of the objects from the DB into RAM.
        """
        for doc_id in self._db:
            self._load_object(doc_id)

    def _load_object(self, doc_id):
        """
        This loads the parent class, instantiates the object through the
        parent class (passing the values from the DB as constructor kwargs).

        :param str doc_id: The CouchDB ID for the object to load.
        """
        # Retrieves the JSON doc from CouchDB.
        doc = self._db[doc_id]
        # Loads the parent class so we can instantiate the object.
        parent = PARENT_LOADER.load_parent(doc['parent'])
        # Instantiate the object, using the values from the DB as kwargs.
        self._objects[doc_id] = parent(**doc)

    def _create_initial_room(self):
        """
        If the initial RoomObject that players login to doesn't exist, create
        it and save it. Loading will be done later.
        """
        parent_path = 'src.game.parents.base_objects.room.RoomObject'
        RoomObject = PARENT_LOADER.load_parent(parent_path)
        room = RoomObject(name='And so it begins...',
                          parent=parent_path)
        self.save_object(room)

    def save_object(self, obj_or_id):
        """
        Saves an object to CouchDB. The odata attribute on each object is
        the raw dict that gets saved to and loaded from CouchDB.
        """
        odata = obj_or_id.odata
        self._db.save(odata)
