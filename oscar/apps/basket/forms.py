from django import forms
from django.conf import settings
from django.db.models import get_model
from django.utils.translation import gettext_lazy as _

Line = get_model('basket', 'line')
Basket = get_model('basket', 'basket')
Product = get_model('catalogue', 'product')


class BasketLineForm(forms.ModelForm):
    save_for_later = forms.BooleanField(initial=False, required=False)

    def clean_quantity(self):
        qty = self.cleaned_data['quantity']
        self.check_max_allowed_quantity(qty)
        self.check_permission(qty)
        return qty

    def check_max_allowed_quantity(self, qty):
        basket_threshold = settings.OSCAR_MAX_BASKET_QUANTITY_THRESHOLD
        if basket_threshold:
            total_basket_quantity = self.instance.basket.num_items
            max_allowed = basket_threshold - total_basket_quantity
            if qty > max_allowed:
                raise forms.ValidationError(
                    _("Due to technical limitations we are not able to ship"
                      " more than %(threshold)d items in one order. Your basket"
                      " currently has %(basket)d items.") % {
                            'threshold': basket_threshold,
                            'basket': total_basket_quantity,
                    })

    def check_permission(self, qty):
        product = self.instance.product
        is_available, reason = product.is_purchase_permitted(user=None,
                                                             quantity=qty)
        if not is_available:
            raise forms.ValidationError(reason)

    class Meta:
        model = Line
        exclude = ('basket', 'product', 'line_reference', 'price_incl_tax')


class SavedLineForm(forms.ModelForm):
    move_to_basket = forms.BooleanField(initial=False, required=False)

    class Meta:
        model = Line
        exclude = ('basket', 'product', 'line_reference', 'quantity', 'price_incl_tax')


class BasketVoucherForm(forms.Form):
    code = forms.CharField(max_length=128)

    def __init__(self, *args, **kwargs):
        return super(BasketVoucherForm, self).__init__(*args,**kwargs)

    def clean_code(self):
        return self.cleaned_data['code'].strip().upper()


class ProductSelectionForm(forms.Form):
    product_id = forms.IntegerField(min_value=1)

    def clean_product_id(self):
        id = self.cleaned_data['product_id']

        try:
            return Product.objects.get(pk=id)
        except Product.DoesNotExist:
            raise forms.ValidationError(_("This product is not available for purchase"))


class AddToBasketForm(forms.Form):
    product_id = forms.IntegerField(widget=forms.HiddenInput(), min_value=1)
    quantity = forms.IntegerField(initial=1, min_value=1)

    def __init__(self, basket, user, instance, *args, **kwargs):
        super(AddToBasketForm, self).__init__(*args, **kwargs)
        self.basket = basket
        self.user = user
        self.instance = instance
        if instance:
            if instance.is_group:
                self._create_group_product_fields(instance)
            else:
                self._create_product_fields(instance)

    def clean(self):
        id = self.cleaned_data['product_id']
        product = Product.objects.get(id=id)
        qty = self.cleaned_data.get('quantity', 1)
        try:
            line = self.basket.lines.get(product=product)
        except Line.DoesNotExist:
            desired_qty = qty
        else:
            desired_qty = qty + line.quantity

        is_available, reason = product.is_purchase_permitted(user=self.user,
                                                             quantity=desired_qty)
        if not is_available:
            raise forms.ValidationError(reason)
        return self.cleaned_data

    def clean_quantity(self):
        qty = self.cleaned_data['quantity']
        basket_threshold = settings.OSCAR_MAX_BASKET_QUANTITY_THRESHOLD
        if basket_threshold:
            total_basket_quantity = self.basket.num_items
            max_allowed = basket_threshold - total_basket_quantity
            if qty > max_allowed:
                raise forms.ValidationError(
                    _("Due to technical limitations we are not able to ship"
                      " more than %(threshold)d items in one order. Your basket"
                      " currently has %(basket)d items.") % {
                            'threshold': basket_threshold,
                            'basket': total_basket_quantity,
                    })
        return qty

    def _create_group_product_fields(self, item):
        """
        Adds the fields for a "group"-type product (eg, a parent product with a
        list of variants.
        """
        choices = []
        for variant in item.variants.all():
            if variant.has_stockrecord:
                summary = u"%s (%s) - %.2f" % (variant.get_title(), variant.attribute_summary(),
                                               variant.stockrecord.price_incl_tax)
                choices.append((variant.id, summary))
        self.fields['product_id'] = forms.ChoiceField(choices=tuple(choices))

    def _create_product_fields(self, item):
        u"""Add the product option fields."""
        for option in item.options:
            self._add_option_field(item, option)

    def _add_option_field(self, item, option):
        u"""
        Creates the appropriate form field for the product option.

        This is designed to be overridden so that specific widgets can be used for
        certain types of options.
        """
        self.fields[option.code] = forms.CharField()


class SimpleAddToBasketForm(AddToBasketForm):
    quantity = forms.IntegerField(initial=1, min_value=1, widget=forms.HiddenInput)

