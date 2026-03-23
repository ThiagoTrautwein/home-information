from hi.apps.entity.models import Entity, EntityView, EntityPosition, EntityPath
from hi.apps.collection.models import CollectionEntity
from django.db.models import Q


class EditViewHelpers:
    """
    Helper utilities for edit mode functionality across all modules.

    Centralizes unused detection logic and other edit-mode utilities to avoid
    circular dependencies between modules. Since this is in the general edit
    module, it can safely depend on entity and collection modules.
    """

    @staticmethod
    def _entity_view_supports_entity_instance() -> bool:
        return EntityView.objects.supports_entity_instance()

    @staticmethod
    def _get_entity_view_entity_ids() -> set:
        """
        Return root entity IDs referenced by EntityView.

        Prefers entity-instance ownership when supported by schema while
        retaining compatibility with legacy direct-entity ownership.
        """
        in_view_ids = set()

        if EditViewHelpers._entity_view_supports_entity_instance():
            entity_view_qs = EntityView.objects.values_list(
                'entity_id',
                'entity_instance__entity_id',
            )

            for entity_id, entity_instance_entity_id in entity_view_qs:
                if entity_id is not None:
                    in_view_ids.add( entity_id )

                if entity_instance_entity_id is not None:
                    in_view_ids.add( entity_instance_entity_id )

            return in_view_ids

        # Legacy schema fallback: EntityView owned only by entity.
        return set( EntityView.objects.values_list( 'entity_id', flat = True ) )

    @staticmethod
    def _entity_has_any_view( entity_id: int ) -> bool:
        return EntityView.objects.for_entity( entity_id ).exists()

    @staticmethod
    def get_unused_entity_ids() -> set:
        """
        Return entity IDs that are neither visible in any location view
        nor in any collection.

        An entity is considered "unused" if it's not accessible through:
        1. Being visible in any location view (has EntityView AND EntityPosition/EntityPath)
        2. Membership in any collection (CollectionEntity)

        For efficiency, we approximate visibility as: has EntityView AND has EntityPosition OR EntityPath
        This may include some entities that aren't truly visible but is much faster to calculate.
        """
        # Get entities that have EntityView records (are in some view)
        in_view_ids = EditViewHelpers._get_entity_view_entity_ids()

        # Get entities that have position or path records
        positioned_ids = set()
        entity_position_qs = EntityPosition.objects.values_list(
            'entity_id',
            'entity_instance__entity_id',
        )

        for entity_id, entity_instance_entity_id in entity_position_qs:
            if entity_id is not None:
                positioned_ids.add(entity_id)

            if entity_instance_entity_id is not None:
                positioned_ids.add(entity_instance_entity_id)
                
        pathed_ids = set()
        entity_path_qs = EntityPath.objects.values_list(
            'entity_id',
            'entity_instance__entity_id',
        )

        for entity_id, entity_instance_entity_id in entity_path_qs:
            if entity_id is not None:
                pathed_ids.add(entity_id)

            if entity_instance_entity_id is not None:
                pathed_ids.add(entity_instance_entity_id)

        has_location_data_ids = positioned_ids | pathed_ids

        # Potentially visible = in a view AND has location data
        potentially_visible_ids = in_view_ids & has_location_data_ids

        # Get entities that are in any collection
        collection_member_ids = set(CollectionEntity.objects.values_list('entity_id', flat=True))

        # Get all entity IDs
        all_entity_ids = set(Entity.objects.values_list('id', flat=True))

        # Unused = not potentially visible AND not in any collection
        accessible_ids = potentially_visible_ids | collection_member_ids
        return all_entity_ids - accessible_ids

    @staticmethod
    def is_entity_unused(entity_id: int) -> bool:
        """
        Check if a single entity is unused (not visible in any location view
        and not in any collection).

        More efficient than get_unused_entity_ids() when checking just one entity.
        """
        # Check if entity is in any view
        has_view = EditViewHelpers._entity_has_any_view(entity_id)
        if not has_view:
            # No view, but check if in collection
            has_collection = CollectionEntity.objects.filter(entity_id=entity_id).exists()
            return not has_collection

        # Has view, check if has location data
        has_position = EntityPosition.objects.for_entity( entity_id ).exists()
        has_path = EntityPath.objects.for_entity( entity_id ).exists()

        if has_position or has_path:
            return False  # Potentially visible

        # Has view but no location data, check if in collection
        has_collection = CollectionEntity.objects.filter(entity_id=entity_id).exists()
        return not has_collection
