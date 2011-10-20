from fuzzywuzzy import fuzz
import couchdb
from couchdb.http import ResourceNotFound

from settings import DATABASES
from src.server.objects.exceptions import InvalidObjectId
from src.server.parent_loader.exceptions import InvalidParent
from src.utils import logger

class InMemoryObjectStore(object):
    """
    Serves as an in-memory object store for all "physical" entities in the
    game. An "object" can be stuff like a room or a thing.
    """
    def __init__(self, mud_service, db_name=None):
        """
        .. warning:: Due to the order this class is instantiated in
            ``dott.tac``, do not interact with self._account_store within
            this constructor, as it won't be set yet.

        :param MudService mud_service: The MudService class running the game.
        :keyword str db_name: Overrides the DB name for the object DB.
        """
        self._mud_service = mud_service
        # Reference to the server's parent loader instance.
        self._parent_loader = mud_service.parent_loader

        # Keys are CouchDB ids, values are the parent instances (children of
        # src.game.parents.base_objects.base.BaseObject
        self._objects = {}

        # Eventually contains a CouchDB reference. Queries come through here.
        self._db = None
        # The string name of the DB.
        self._db_name = db_name
        # Reference to CouchDB server connection.
        self._server = None

        # This is used to determine what the next dbref number will be.
        # It's initially set at start time, then incremented as new objects
        # are created.
        self.__next_dbref = 1

    @property
    def _session_manager(self):
        """
        Short-cut to the global session manager.

        :rtype: SessionManager
        :returns: Reference to the global session manager instance.
        """
        #noinspection PyUnresolvedReferences
        return self._mud_service.session_manager

    @property
    def _account_store(self):
        """
        Short-cut to the global account store.

        :rtype: InMemoryAccountStore
        :returns: Reference to the global account store instance.
        """
        #noinspection PyUnresolvedReferences
        return self._mud_service.account_store

    @property
    def _command_handler(self):
        """
        Short-cut to the global command handler.

        :rtype: CommandHandler
        :returns: Reference to the global command handler instance.
        """
        return self._mud_service.command_handler

    def _prepare_at_load(self):
        """
        Prepares the store for duty.
        """
        # Just in case this is a code reload.
        self._objects = {}
        # Reference to CouchDB server connection.
        self._server = couchdb.Server()
        # Loads or creates+loads the CouchDB database.
        self._prep_db(db_name=self._db_name)
        # Loads all of the objects into RAM from CouchDB.
        self._load_objects_into_ram()

    def _prep_db(self, db_name=None):
        """
        Sets the :attr:`_db` reference. Creates the CouchDB if the requested
        one doesn't exist already.

        :keyword str db_name: Overrides the DB name for the object DB.
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

            # See if this is the new highest dbref.
            doc_id_int = int(doc_id)
            if doc_id_int >= self.__next_dbref:
                self.__next_dbref = doc_id_int + 1

    def _load_object(self, doc_id):
        """
        This loads the parent class, instantiates the object through the
        parent class (passing the values from the DB as constructor kwargs).

        :param str doc_id: The CouchDB ID for the object to load.
        :rtype: BaseObject
        :returns: The newly loaded object.
        """
        # Retrieves the JSON doc from CouchDB.
        doc = self._db[doc_id]
        # Loads the parent class so we can instantiate the object.
        try:
            parent = self._parent_loader.load_parent(doc['parent'])
        except InvalidParent:
            # Get more specific with the exception output in this case. This
            # will give us an object ID to look at in the logs.
            raise InvalidParent(
                'Attempting to load invalid parent on object #%s: %s' % (
                    doc_id,
                    doc['parent'],
                )
            )
        # Instantiate the object, using the values from the DB as kwargs.
        self._objects[doc_id] = parent(self._mud_service, **doc)
        return self._objects[doc_id]

    def _create_initial_room(self):
        """
        If the initial RoomObject that players login to doesn't exist, create
        it and save it. Loading will be done later.
        """
        parent_path = 'src.game.parents.base_objects.room.RoomObject'
        self.create_object(parent_path, name='And so it begins...')

    def create_object(self, parent_path, **kwargs):
        """
        Creates and saves a new object of the specified parent.

        :param str parent_path: The full Python path + class name for a parent.
            for example, src.game.parents.base_objects.room.RoomObject.
        :keyword dict kwargs: Additional attributes to set on the object.
        :rtype: BaseObject
        :returns: The newly created/instantiated/saved object.
        """
        NewObject = self._parent_loader.load_parent(parent_path)
        obj = NewObject(
            self._mud_service,
            _id='%s' % self.__next_dbref,
            parent=parent_path,
            **kwargs
        )
        obj.save()
        # Increment the next dbref counter for the next object.
        self.__next_dbref += 1
        return obj

    def save_object(self, obj):
        """
        Saves an object to CouchDB. The _odata attribute on each object is
        the raw dict that gets saved to and loaded from CouchDB.

        :param BaseObject obj: The object to save to the DB.
        """
        odata = obj._odata
        # Saves to CouchDB.
        id, rev = self._db.save(odata)
        # For new objects, update our in-memory object with the newly assigned
        # _id in CouchDB.
        obj._id = id
        # Update our in-memory cache with the saved object.
        self._objects[odata['_id']] = obj

    def destroy_object(self, obj):
        """
        Destroys an object by yanking it from :py:attr:`_objects` and CouchDB.
        """
        del self._db[obj.id]
        del self._objects[obj.id]
        del obj

    def reload_object(self, obj):
        """
        Re-loads the object from CouchDB.

        :param BaseObject obj: The object to re-load from the DB.
        :rtype: BaseObject
        :returns: The newly re-loaded object.
        """
        obj_id = obj.id
        del self._objects[obj_id]
        return self._load_object(obj_id)

    def get_object(self, obj_id):
        """
        Given an object ID, return the object's instance.

        :param str obj_id: The ID of the object to return.
        :returns: The requested object, which will be a :class:`BaseObject`
            sub-class of some sort.
        :raises: :py:exc:`src.server.objects.exceptions.InvalidObjectId` if
            no object with the requested ID exists.
        """
        try:
            return self._objects[str(obj_id)]
        except KeyError:
            raise InvalidObjectId(
                'Invalid object ID requested: %s' % str(obj_id)
            )

    def get_object_contents(self, obj):
        """
        Returns all objects inside of the specified object.

        :param BaseObject obj: The object whose contents to calculate.
        :rtype: list
        :returns: A list of BaseObject instances whose current location
            is ``obj``.
        """
        return [omatch for omatch in self._objects.values() if omatch.location == obj]

    def global_name_search(self, name):
        """
        Does a global name search of all objects. Compares input to the name
        odata key on all objects.

        :param str name: The name to search for.
        :returns: A generator of ``BaseObject`` matches.
        """
        for id, obj in self._objects.iteritems():
            ratio = fuzz.partial_ratio(name, obj.name)
            if ratio > 50:
                yield obj

    def find_exits_linked_to_obj(self, obj):
        """
        Finds all exits that are linked to the given object.

        :param BaseObject obj: The object which to find linked exits to.
        :rtype: list
        :return: A list of exits that are linked to the given object.
        """
        if obj.base_type == 'exit':
            # Exits can't be linked to one another, this ends up being invalid.
            return []

        # We could use a generator for this, but then we couldn't iterate
        # and delete as we went, as this would change the size of self._objects
        # during the iteration (causing an exception). So store in list.
        linked_exits = []
        for id, db_obj in self._objects.iteritems():
            if not db_obj.base_type == 'exit':
                # Not an exit, not interested.
                continue

            destination = db_obj.destination
            if destination and destination.id == obj.id:
                # This object's destination matches the specified object's ID.
                linked_exits.append(db_obj)

        return linked_exits

    def find_objects_in_zone(self, obj):
        """
        Finds all objects whose zone master object is set to the given object.

        :param BaseObject obj: The object whose zone members to find.
        :rtype: list
        :return: A list of the object's zone members.
        """
        # We could use a generator for this, but then we couldn't iterate
        # and delete as we went, as this would change the size of self._objects
        # during the iteration (causing an exception). So store in list.
        zone_members = []
        for id, db_obj in self._objects.iteritems():
            zone = db_obj.zone
            if zone and zone.id == obj.id:
                # This object's zone matches the specified object's ID.
                zone_members.append(db_obj)

        return zone_members