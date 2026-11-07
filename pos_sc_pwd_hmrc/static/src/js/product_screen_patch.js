/** @odoo-module **/

import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
import { patch } from "@web/core/utils/patch";
import { SpecialDiscountButtons } from "./special_discount_buttons";

// Make SpecialDiscountButtons available to ProductScreen template
patch(ProductScreen.prototype, {
    setup() {
        super.setup();
        this.SpecialDiscountButtons = SpecialDiscountButtons;
    }
});

// Export for template usage
ProductScreen.components = {
    ...ProductScreen.components,
    SpecialDiscountButtons,
};