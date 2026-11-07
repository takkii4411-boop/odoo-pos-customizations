/** @odoo-module **/

import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { ErrorPopup } from "@point_of_sale/app/errors/popups/error_popup";
import { DiscountTypeSelectionPopup, ManagerApprovalPopup } from "./discount_modal";
import { NumberPopup } from "@point_of_sale/app/utils/input_popups/number_popup";

patch(ProductScreen.prototype, {
    /**
     * Override the discount button click to show our modal system
     */
    async onNumpadClick(buttonValue) {
        // Intercept when user clicks the discount button (%)
        if (buttonValue === 'discount') {
            const order = this.pos.get_order();
            const partner = order?.get_partner();

            // Check if customer is eligible for special discounts
            if (partner && partner.senior_pwd_person !== '') {
                // Show discount type selection modal
                const { confirmed, payload: discountType } = await this.popup.add(DiscountTypeSelectionPopup, {});

                if (!confirmed) {
                    return; // User cancelled
                }

                if (discountType === 'regular') {
                    // Regular discount - use default behavior (numeric input)
                    return super.onNumpadClick(...arguments);
                } else if (discountType === 'special') {
                    // Special discount - show manager approval modal
                    const { confirmed: approved, payload: approvalData } = await this.popup.add(ManagerApprovalPopup, {});

                    if (approved) {
                        // Manager approved - special discount mode is now enabled for this order
                        console.log('[Discount Modal] Manager approved special discount mode');
                        // UI will automatically update through reactivity
                    }
                    return; // Don't apply numeric discount
                }
            }
        }

        // Default behavior for all other buttons and non-eligible customers
        return super.onNumpadClick(...arguments);
    },
});