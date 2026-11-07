/** @odoo-module **/

import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { ErrorPopup } from "@point_of_sale/app/errors/popups/error_popup";
import { useService } from "@web/core/utils/hooks";

patch(ProductScreen.prototype, {
    setup() {
        super.setup();
        this.errorPopup = useService("popup");
    },

    /**
     * Override changeMode to prevent discount changes for special discount lines
     */
    async changeMode(mode) {
        // Check if trying to apply discount
        if (mode === 'discount') {
            const order = this.pos.get_order();
            const selectedLine = order?.get_selected_orderline();

            // Check if line has special discount applied
            if (selectedLine && selectedLine.is_sc_line) {
                await this.popup.add(ErrorPopup, {
                    title: _t("Discount Locked"),
                    body: _t("Cannot modify percentage discount for lines with special discounts applied. Remove the special discount first if you want to apply a different discount."),
                });
                return; // Prevent changing to discount mode
            }
        }

        // Call original method
        return super.changeMode(...arguments);
    },
});