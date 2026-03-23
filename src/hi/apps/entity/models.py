import json
from typing import Dict, List, Optional, Tuple, Union

from django.db import models

from hi.apps.location.models import (
    Location,
    LocationItemModelMixin,
    LocationItemPositionModel,
    LocationItemPathModel,
    LocationView,
)
from hi.apps.attribute.models import AttributeModel, AttributeValueHistoryModel
from hi.integrations.models import IntegrationDetailsModel
from hi.enums import ItemType

from .enums import (
    EntityType,
    EntityStateType,
)


class Entity( IntegrationDetailsModel, LocationItemModelMixin ):
    """
    - A physical feature, device or software artifact.
    - May have a fixed physical location (or can just be part of a collection)
    - Maybe be located at a specific point or defined by an SVG path (e.g., paths for wire, pipes, etc.) 
    - It may have zero or more EntityStates.
    - The entity state values are always hidden.
    - A state may have zero of more sensors to report the state values.
    - Each sensor reports the value for a single state.
    - Each sensors reports state from a space of discrete or continuous values (or a blob).
    - A state may have zero or more controllers.
    - Each controller may control 
    - Its 'EntityType' determines is visual appearance.
    - An entity can have zero or more staticly defined attributes (for information and configuration)
    """
    
    name = models.CharField(
        'Name',
        max_length = 64,
        null = False, blank = False,
    )
    entity_type_str = models.CharField(
        'Entity Type',
        max_length = 32,
        null = False, blank = False,
    )    
    can_user_delete = models.BooleanField(
        'User Delete?',
        default = True,
    )
    has_video_stream = models.BooleanField(
        'Has Video Stream',
        default = False,
    )
    created_datetime = models.DateTimeField(
        'Created',
        auto_now_add = True,
    )

    class Meta:
        verbose_name = 'Entity'
        verbose_name_plural = 'Entities'
        constraints = [
            models.UniqueConstraint(
                fields = [ 'integration_id', 'integration_name' ],
                name = 'entity_integration_key',
            ),
        ]

    def __str__(self):
        return f'{self.name} ({self.entity_type_str}) [{self.id}]'
    
    def __repr__(self):
        return self.__str__()
    
    @property
    def item_type(self) -> ItemType:
        return ItemType.ENTITY
    
    @property
    def entity_type(self) -> EntityType:
        return EntityType.from_name_safe( self.entity_type_str )

    @entity_type.setter
    def entity_type( self, entity_type : EntityType ):
        self.entity_type_str = str(entity_type)
        return

    def get_attribute_map(self):
        attribute_map = dict()
        for attribute in self.attributes.all():
            attribute_map[attribute.name] = attribute
            continue
        return attribute_map

    def shallow_copy( self, share_states : bool = True ) -> 'EntityInstance':
        """Creates a shallow visual copy of this Entity as an EntityInstance.

        When ``share_states`` is false, clones state definitions so the instance
        has its own independent EntityState records.
        """
        entity_instance = self.instances.create(
            share_states = share_states,
        )

        if not share_states:
            for entity_state in EntityState.objects.for_entity( self ):
                entity_state.clone_for_entity_instance( entity_instance )

        return entity_instance


class EntityAttribute( AttributeModel ):
    """
    - Information related to an entity, e.g., specs, docs, notes, configs
    - The 'attribute type' is used to help define what information the user might need to provide.
    """
    
    entity = models.ForeignKey(
        Entity,
        related_name = 'attributes',
        verbose_name = 'Entity',
        on_delete = models.CASCADE,
    )

    class Meta:
        verbose_name = 'Attribute'
        verbose_name_plural = 'Attributes'
        indexes = [
            models.Index( fields=[ 'name', 'value' ] ),
        ]
        ordering = ['order_id', 'id']

    def get_upload_to(self):
        return 'entity/attributes/'
    
    def _get_history_model_class(self):
        """Return the history model class for EntityAttribute."""
        return EntityAttributeHistory


class EntityInstance( models.Model ):

    entity = models.ForeignKey(
        Entity,
        on_delete = models.CASCADE,
        related_name = "instances"
    )

    share_states = models.BooleanField(
        'Share States?',
        default = True
    )

    created_datetime = models.DateTimeField(
        'Created',
        auto_now_add = True
    )

    @property
    def state_owner(self) -> Union[ Entity, 'EntityInstance' ]:
        if self.share_states:
            return self.entity
        return self

    def get_states(self):
        return EntityState.objects.for_entity_instance( self )


class EntityOwnedStateQuerySet( models.QuerySet ):

    def for_entity( self, entity_or_id: Union[Entity, int] ):
        entity_id = entity_or_id.id if hasattr( entity_or_id, 'id' ) else int( entity_or_id )
        return self.filter(
            entity_id = entity_id,
            entity_instance__isnull = True,
        )

    def for_entity_instance( self, entity_instance_or_id: Union[EntityInstance, int] ):
        entity_instance = entity_instance_or_id
        if not hasattr( entity_instance_or_id, 'id' ):
            try:
                entity_instance = EntityInstance.objects.select_related( 'entity' ).get(
                    id = int( entity_instance_or_id ),
                )
            except ( TypeError, ValueError, EntityInstance.DoesNotExist ):
                return self.none()

        if entity_instance.share_states:
            return self.for_entity( entity_instance.entity_id )

        return self.filter(
            entity = None,
            entity_instance_id = entity_instance.id,
        )


class EntityStateManager( models.Manager ):

    def get_queryset( self ):
        return EntityOwnedStateQuerySet( self.model, using = self._db )

    def for_entity( self, entity_or_id: Union[Entity, int] ):
        return self.get_queryset().for_entity( entity_or_id )

    def for_entity_instance( self, entity_instance_or_id: Union[EntityInstance, int] ):
        return self.get_queryset().for_entity_instance( entity_instance_or_id )

    def create_for_entity_instance( self,
                                    entity_instance: EntityInstance,
                                    entity_state_type_str: str,
                                    name: str,
                                    value_range_str: str = None,
                                    units: str = None ):
        return self.create(
            entity = None,
            entity_instance = entity_instance,
            entity_state_type_str = entity_state_type_str,
            name = name,
            value_range_str = value_range_str,
            units = units,
        )

        
class EntityState( models.Model ):
    """
    - The (hidden) state of an entity that can be controlled and/or sensed.
    - The EntityType will help define the (default) name and value ranges (if not a general type)
    """
    
    entity = models.ForeignKey(
        Entity,
        related_name = 'states',
        verbose_name = 'Entity',
        on_delete = models.CASCADE,
        null = True,
        blank = True,
    )
    entity_instance = models.ForeignKey(
        EntityInstance,
        related_name = 'states',
        verbose_name = 'Entity Instance',
        on_delete = models.CASCADE,
        null = True,
        blank = True,
    )
    entity_state_type_str = models.CharField(
        'State Type',
        max_length = 32,
        null = False, blank = False,
        db_index = True,
    )
    name = models.CharField(
        'Name',
        max_length = 64,
        null = False, blank = False,
    )
    value_range_str = models.TextField(
        'Value Range',
        null = True, blank = True,
    )
    units = models.CharField(
        'Units',
        max_length = 32,
        null = True, blank = True,
    )
    created_datetime = models.DateTimeField(
        'Created',
        auto_now_add = True,
    )

    objects = EntityStateManager()
    
    class Meta:
        verbose_name = 'Entity State'
        verbose_name_plural = 'Entity States'
        constraints = [
            models.CheckConstraint(
                check = (
                    ( models.Q( entity__isnull = False ) & models.Q( entity_instance__isnull = True ) )
                    | ( models.Q( entity__isnull = True ) & models.Q( entity_instance__isnull = False ) )
                ),
                name = 'entity_state_exactly_one_owner',
            ),
        ]
        
    def __str__(self):
        return f'{self.name}[{self.id}] ({self.entity_state_type_str})'
    
    def __repr__(self):
        return self.__str__()

    @property
    def owner(self) -> Union[ Entity, EntityInstance ]:
        if self.entity:
            return self.entity
        return self.entity_instance

    @property
    def root_entity(self) -> Entity:
        if self.entity:
            return self.entity
        return self.entity_instance.entity
    
    @property
    def entity_state_type(self):
        return EntityStateType.from_name_safe( self.entity_state_type_str )

    @entity_state_type.setter
    def entity_state_type( self, entity_state_type : EntityStateType ):
        self.entity_state_type_str = str(entity_state_type)
        return

    @property
    def css_class(self):
        return f'hi-entity-state-{self.id}'

    @property
    def value_range_dict(self):
        try:
            value_range = json.loads( self.value_range_str )
            if isinstance( value_range, dict ):
                return value_range
            if isinstance( value_range, list ):
                return { x: x for x in value_range }
        except json.JSONDecodeError:
            pass
        return dict()

    @value_range_dict.setter
    def value_range_dict( self, value_dict : Dict[ str, str ] ):
        self.value_range_str = json.dumps( value_dict )
        return

    def choices(self) -> List[ Tuple[str,str] ]:
        if self.value_range_str:
            try:
                value_range = json.loads( self.value_range_str )
                if (( len(value_range) == 2 )
                    and ( 'min' in value_range )
                    and ( 'max' in value_range )):
                    return list()
                if isinstance( value_range, dict ):
                    return [ ( str(k), str(v) ) for k, v in value_range.items() ]
                if isinstance( value_range, list ):
                    return [ ( str(x), str(x) ) for x in value_range ]
            except json.JSONDecodeError:
                pass
        return self.entity_state_type.choices()

    def toggle_values(self) -> List[str]:
        if self.value_range_str:
            try:
                # Special case for min/max types to allow toggling extremes (e.g., dimmer switches)
                value_range = json.loads( self.value_range_str )
                if (( len(value_range) == 2 )
                    and ( 'min' in value_range )
                    and ( 'max' in value_range )):
                    return [ str(value_range['min']), str(value_range['max']) ]
                
                if isinstance( value_range, dict ):
                    return [ str(k) for k, v in value_range.items() ]
                if isinstance( value_range, list ):
                    return [ str(x) for x in value_range ]
            except json.JSONDecodeError:
                pass
        return self.entity_state_type.toggle_values()
    
    def to_toggle_value( self, actual_value : str ) -> str:
        # Special case for min/max types to allow toggling extremes (e.g., dimmer switches)
        if self.value_range_str:
            try:
                value_range = json.loads( self.value_range_str )
                if (( len(value_range) == 2 )
                    and ( 'min' in value_range )
                    and ( 'max' in value_range )):
                    min_value = value_range['min']
                    max_value = value_range['max']
                    if actual_value and ( float(actual_value) > float(min_value) ):
                        return str(max_value)
                    return str(min_value)
            except ( TypeError, ValueError, json.JSONDecodeError ):
                pass
        return actual_value

    def clone_for_entity_instance( self, entity_instance : EntityInstance ) -> 'EntityState':
        return EntityState.objects.create_for_entity_instance(
            entity_instance = entity_instance,
            entity_state_type_str = self.entity_state_type_str,
            name = self.name,
            value_range_str = self.value_range_str,
            units = self.units,
        )

        
class EntityStateDelegation(models.Model):
    """An EntityState associated with a Sensor or Controller is often serving
    representing the state of some other entity. In those cases, the entity
    containing the sensors/controllers is really just a proxy for some
    other entity's (hidden) state.  If we want to explicitly represent that
    relationship between two entities, we can define a delegation where some
    other entity becomes the "delegate" and the original entity containing the
    sensor/controller being the "principal".

        e.g., An open/close switch entity with an open/close sensor is
        directly sensing the state of the switch in the device, but it is
        indirectly trying to sense the state of a door or window. Thus, the
        door open/close "state" is being proxied by the open/close sensor's
        swith.  The open/close swith device is the principal entity while
        the door/window is the delegate entity.

        e.g., A sprinkler controller valve is directly sensing and controlling
        whether it is on or off, but also serves as a proxy for all the
        sprinkler heads connected to it.

        e.g., A temperature sensor's internal temperature states is really just
        a proxy for a area (and a Area is also an Entity).

        e.g., A motion detectors's internal "movement" state about reflected
        infrared signals is just a proxy for movement associated with a Area.

    This delegation relationship between an Entities can either be
    one-to-many or many-to-one.
    
        e.g., A thermostat may be aggregating the readings from multiple
        remote sensors so that the internal temperature state of the
        thermostat is a proxy for all the remote sensor states.

    The purpose of representing the delegation relationships is to allow
    visually changing the display of an Entity based on the sensors
    that are serving as a proxy for it.  It also allows clicks/taps on the delegate
    entity to be associated with the sensors or controllers that are proxying 
    for it.  

        e.g., A common case is for defining "Area" entities and visually
        displaying them so that they can change colors based on movement
        sensors that proxy for the area and showing the video stream for
        the camera entity proxying for the area.

    """
    
    entity_state = models.ForeignKey(
        EntityState,
        related_name = 'entity_state_delegations',
        verbose_name = 'Entity State',
        on_delete = models.CASCADE,
    )
    delegate_entity = models.ForeignKey(
        Entity,
        related_name = 'entity_state_delegations',
        verbose_name = 'Deleage Entity',
        on_delete = models.CASCADE,
    )
    created_datetime = models.DateTimeField(
        'Created',
        auto_now_add = True,
    )

    class Meta:
        verbose_name = 'Entity State Delegation'
        verbose_name_plural = 'Entity State Delegations'
        constraints = [
            models.UniqueConstraint(
                fields = [ 'delegate_entity', 'entity_state' ],
                name = 'entity_state_delegation_uniqueness',
            ),
        ]


class EntityOwnedLocationItemQuerySet( models.QuerySet ):

    def for_entity( self, entity_or_id: Union[Entity, int] ):
        entity_id = entity_or_id.id if hasattr( entity_or_id, 'id' ) else int( entity_or_id )
        return self.filter(
            (
                models.Q( entity_id = entity_id )
                & models.Q( entity_instance__isnull = True )
            )
            | (
                models.Q( entity__isnull = True )
                & models.Q( entity_instance__entity_id = entity_id )
            )
        )

    def with_owner_priority( self ):
        # Prefer legacy direct-owner rows if both representations exist.
        return self.order_by( '-entity_id', 'id' )

    def for_entity_instance( self, entity_instance_or_id: Union[EntityInstance, int] ):
        entity_instance_id = ( entity_instance_or_id.id
                               if hasattr( entity_instance_or_id, 'id' )
                               else int( entity_instance_or_id ) )
        return self.filter(
            entity = None,
            entity_instance_id = entity_instance_id,
        )


class EntityPositionManager( models.Manager ):

    def get_queryset( self ):
        return EntityOwnedLocationItemQuerySet( self.model, using = self._db )

    def for_entity( self, entity_or_id: Union[Entity, int] ):
        return self.get_queryset().for_entity( entity_or_id )

    def for_entity_instance( self, entity_instance_or_id: Union[EntityInstance, int] ):
        return self.get_queryset().for_entity_instance( entity_instance_or_id )

    def create_for_entity_instance( self,
                                    entity_instance: EntityInstance,
                                    location: Location,
                                    svg_x,
                                    svg_y,
                                    svg_scale,
                                    svg_rotate ):
        return self.create(
            entity = None,
            entity_instance = entity_instance,
            location = location,
            svg_x = svg_x,
            svg_y = svg_y,
            svg_scale = svg_scale,
            svg_rotate = svg_rotate,
        )


class EntityPathManager( models.Manager ):

    def get_queryset( self ):
        return EntityOwnedLocationItemQuerySet( self.model, using = self._db )

    def for_entity( self, entity_or_id: Union[Entity, int] ):
        return self.get_queryset().for_entity( entity_or_id )

    def for_entity_instance( self, entity_instance_or_id: Union[EntityInstance, int] ):
        return self.get_queryset().for_entity_instance( entity_instance_or_id )

    def create_for_entity_instance( self,
                                    entity_instance: EntityInstance,
                                    location: Location,
                                    svg_path: str ):
        return self.create(
            entity = None,
            entity_instance = entity_instance,
            location = location,
            svg_path = svg_path,
        )
    
    
class EntityPosition( LocationItemPositionModel ):
    """
    - For entities represented by an SVG icon.
    - This is the most common case.
    - The icon and its styling determined by the EntityType. 
    - An Entity is not required to have an EntityPosition.
    """
    
    location = models.ForeignKey(
        Location,
        related_name = 'entity_positions',
        verbose_name = 'Location',
        on_delete = models.CASCADE,
    )
    entity = models.ForeignKey(
        Entity,
        related_name = 'positions',
        verbose_name = 'Entity',
        on_delete = models.CASCADE,
        null = True
    )
    entity_instance = models.ForeignKey(
        EntityInstance,
        related_name = 'positions',
        verbose_name = 'Entity Instance',
        on_delete = models.CASCADE,
        null = True,
        blank = True,
    )
    created_datetime = models.DateTimeField(
        'Created',
        auto_now_add = True,
    )
    updated_datetime = models.DateTimeField(
        'Updated',
        auto_now=True,
        blank = True,
    )

    objects = EntityPositionManager()

    class Meta:
        verbose_name = 'Entity Position'
        verbose_name_plural = 'Entity Positions'
        constraints = [
            models.UniqueConstraint(
                fields = [ 'location', 'entity' ],
                condition = models.Q( entity__isnull = False ),
                name = 'entity_position_location_entity',
            ),
            models.UniqueConstraint(
                fields = [ 'location', 'entity_instance' ],
                condition = models.Q( entity_instance__isnull = False ),
                name = 'entity_position_location_entity_instance',
            ),
            models.CheckConstraint(
                check = (
                    ( models.Q( entity__isnull = False ) & models.Q( entity_instance__isnull = True ) )
                    | ( models.Q( entity__isnull = True ) & models.Q( entity_instance__isnull = False ) )
                ),
                name = 'entity_position_exactly_one_owner',
            ),
        ]
            
    @property
    def location_item(self) -> LocationItemModelMixin:
        return self.entity_instance if self.entity_instance else self.entity

    
class EntityPath( LocationItemPathModel ):
    """
    - For entities represented by an arbitary SVG path. e.g., The path of a utility line, 
    - The styling of the path is determined by the EntityType. 
    - An Entity is not required to have an EntityPath.  
    """
    
    location = models.ForeignKey(
        Location,
        related_name = 'entity_paths',
        verbose_name = 'Location',
        on_delete = models.CASCADE,
    )
    entity = models.ForeignKey(
        Entity,
        related_name = 'paths',
        verbose_name = 'Entity',
        on_delete = models.CASCADE,
        null = True,
    )
    entity_instance = models.ForeignKey(
        EntityInstance,
        related_name = 'paths',
        verbose_name = 'Entity Instance',
        on_delete = models.CASCADE,
        null = True,
        blank = True,
    )
    created_datetime = models.DateTimeField(
        'Created',
        auto_now_add = True,
    )
    updated_datetime = models.DateTimeField(
        'Updated',
        auto_now=True,
        blank = True,
    )

    objects = EntityPathManager()

    class Meta:
        verbose_name = 'Entity Path'
        verbose_name_plural = 'Entity Paths'
        constraints = [
            models.UniqueConstraint(
                fields = [ 'location', 'entity' ],
                condition = models.Q( entity__isnull = False ),
                name = 'entity_path_location_entity', ),
            models.UniqueConstraint(
                fields = [ 'location', 'entity_instance' ],
                condition = models.Q( entity_instance__isnull = False ),
                name = 'entity_path_location_entity_instance',
            ),
            models.CheckConstraint(
                check = (
                    ( models.Q( entity__isnull = False ) & models.Q( entity_instance__isnull = True ) )
                    | ( models.Q( entity__isnull = True ) & models.Q( entity_instance__isnull = False ) )
                ),
                name = 'entity_path_exactly_one_owner',
            ),
        ]
            
    @property
    def location_item(self) -> LocationItemModelMixin:
        return self.entity_instance if self.entity_instance else self.entity


class EntityViewQuerySet( models.QuerySet ):

    def supports_entity_instance( self ) -> bool:
        return any( field.name == 'entity_instance' for field in self.model._meta.get_fields() )

    def for_entity( self, entity_or_id: Union[Entity, int] ):
        entity_id = entity_or_id.id if hasattr( entity_or_id, 'id' ) else int( entity_or_id )

        if self.supports_entity_instance():
            return self.filter(
                models.Q( entity_id = entity_id )
                | models.Q( entity_instance__entity_id = entity_id )
            )

        return self.filter( entity_id = entity_id )

    def with_owner_priority( self ):
        if self.supports_entity_instance():
            # Prefer legacy direct-owner rows if both representations exist.
            return self.order_by( '-entity_id', 'id' )
        return self.order_by( 'id' )


class EntityViewManager( models.Manager ):

    def get_queryset( self ):
        return EntityViewQuerySet( self.model, using = self._db )

    def supports_entity_instance( self ) -> bool:
        return self.get_queryset().supports_entity_instance()

    def for_entity( self, entity_or_id: Union[Entity, int] ):
        return self.get_queryset().for_entity( entity_or_id )

    def with_owner_priority( self ):
        return self.get_queryset().with_owner_priority()

    def _get_or_create_primary_entity_instance( self, entity: Entity ) -> EntityInstance:
        entity_instance = entity.instances.order_by( 'id' ).first()
        if entity_instance:
            return entity_instance
        return entity.instances.create( share_states = True )

    def create_for_entity( self, entity: Entity, location_view: LocationView ):
        if self.supports_entity_instance():
            entity_instance = self._get_or_create_primary_entity_instance( entity )
            return self.create(
                entity = None,
                entity_instance = entity_instance,
                location_view = location_view,
            )

        return self.create(
            entity = entity,
            location_view = location_view,
        )

    
class EntityView(models.Model):

    entity = models.ForeignKey(
        Entity,
        related_name = 'entity_views',
        verbose_name = 'Entity',
        on_delete = models.CASCADE,
    )
    location_view = models.ForeignKey(
        LocationView,
        related_name = 'entity_views',
        verbose_name = 'Location',
        on_delete = models.CASCADE,
    )
    created_datetime = models.DateTimeField(
        'Created',
        auto_now_add = True,
    )

    objects = EntityViewManager()

    class Meta:
        verbose_name = 'Entity View'
        verbose_name_plural = 'Entity Views'

        constraints = [
            models.UniqueConstraint(
                fields = [ 'entity', 'location_view' ],
                name = 'entity_view_entity_location_view', ),
        ]

    @property
    def root_entity( self ) -> Optional[Entity]:
        if self.entity:
            return self.entity

        entity_instance_id = getattr( self, 'entity_instance_id', None )
        if entity_instance_id:
            return self.entity_instance.entity

        return None


class EntityAttributeHistory(AttributeValueHistoryModel):
    """History tracking for EntityAttribute changes."""
    
    attribute = models.ForeignKey(
        EntityAttribute,
        related_name='history',
        verbose_name='Entity Attribute',
        on_delete=models.CASCADE,
    )

    class Meta:
        verbose_name = 'Entity Attribute History'
        verbose_name_plural = 'Entity Attribute History'
        indexes = [
            models.Index(fields=['attribute', '-changed_datetime']),
        ]

