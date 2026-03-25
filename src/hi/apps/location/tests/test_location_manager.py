import logging

from hi.apps.entity.enums import EntityType
from hi.apps.entity.models import Entity, EntityPosition, EntityView
from hi.apps.location.location_manager import LocationManager
from hi.apps.location.models import Location
from hi.testing.base_test_case import BaseTestCase

logging.disable(logging.CRITICAL)


class TestLocationManager(BaseTestCase):

    def test_get_location_view_data_orders_entity_positions_by_z_order_id(self):
        location = Location.objects.create(
            name='Test Location',
            svg_fragment_filename='test.svg',
            svg_view_box_str='0 0 100 100',
        )
        location_view = LocationManager().create_location_view(
            location=location,
            name='Main',
        )

        lower = Entity.objects.create(
            name='Lower',
            entity_type_str=str(EntityType.LIGHT),
        )
        higher = Entity.objects.create(
            name='Higher',
            entity_type_str=str(EntityType.LIGHT),
        )

        EntityView.objects.create(entity=higher, location_view=location_view)
        EntityView.objects.create(entity=lower, location_view=location_view)

        EntityPosition.objects.create(
            entity=lower,
            location=location,
            svg_x=10.0,
            svg_y=10.0,
            svg_rotate=0.0,
            svg_scale=1.0,
            z_order_id=0,
        )
        EntityPosition.objects.create(
            entity=higher,
            location=location,
            svg_x=10.0,
            svg_y=10.0,
            svg_rotate=0.0,
            svg_scale=1.0,
            z_order_id=10,
        )

        location_view_data = LocationManager().get_location_view_data(
            location_view=location_view,
            include_status_display_data=False,
        )

        ordered_entities = [x.entity for x in location_view_data.entity_positions]
        self.assertEqual(ordered_entities, [lower, higher])
