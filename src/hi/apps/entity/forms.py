from django import forms

from hi.apps.attribute.forms import AttributeForm, AttributeUploadForm, RegularAttributeBaseFormSet
from hi.apps.entity.enums import EntityType
from hi.apps.entity.models import Entity, EntityAttribute


class EntityForm( forms.ModelForm ):

    class Meta:
        model = Entity
        fields = (
            'name',
            'entity_type_str',
        )
        
    entity_type_str = forms.ChoiceField(
        label = 'Type',
        choices = EntityType.choices,
        initial = EntityType.default_value(),
        required = True,
        widget = forms.Select( attrs = { 'class' : 'custom-select' } ),
    )
    clone_count = forms.IntegerField(
        label = 'Quantity',
        required = False,
        min_value = 1,
        max_value = 64,
        initial = 1,
    )
    clone_share_states = forms.BooleanField(
        label = 'Share state with clones',
        required = False,
        initial = True,
    )

    
class EntityAttributeForm( AttributeForm ):
    class Meta( AttributeForm.Meta ):
        model = EntityAttribute


EntityAttributeRegularFormSet = forms.inlineformset_factory(
    Entity,
    EntityAttribute,
    form = EntityAttributeForm,
    formset = RegularAttributeBaseFormSet,
    extra = 1,
    max_num = 100,
    absolute_max = 100,
    can_delete = True,
)


class EntityAttributeUploadForm( AttributeUploadForm ):
    class Meta( AttributeUploadForm.Meta ):
        model = EntityAttribute
