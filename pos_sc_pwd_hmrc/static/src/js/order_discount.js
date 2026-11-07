/** @odoo-module **/

import { Order } from "@point_of_sale/app/store/models";
import { patch } from "@web/core/utils/patch";

patch(Order.prototype, {

    /**
     * Refactored add_product to use centralized discount system
     * Handles:
     * 1. Auto-apply discount when toggle is ON
     * 2. Refund scenarios - preserves discounts from original order
     */
    async add_product(product, options) {
        await super.add_product(...arguments);

        const orderline = this.get_selected_orderline();

        // Handle refund scenario: Apply basic necessity discount when passed from options
        if (options?.is_sc_line && options?.is_sc_bnpc_discount) {
            const bnpcConfig = this.pos.getDiscountConfig('bnpc');
            if (bnpcConfig) {
                orderline.applyDiscountFromConfig(bnpcConfig);
            } else {
                orderline.apply_basic_necessity_discount();
            }
            return;
        }

        // Handle refund scenario: Apply SC/PWD discount based on options
        if (options?.is_sc_line) {
            if (options.is_sc_line_discount || options.is_pwd_line_discount) {
                const discountCode = options.is_sc_line_discount ? 'senior' : 'pwd';
                const discountConfig = this.pos.getDiscountConfig(discountCode);

                if (discountConfig) {
                    orderline.applyDiscountFromConfig(discountConfig);
                } else {
                    // Fallback to legacy method
                    if (options.is_sc_line_discount) {
                        orderline.is_sc_line_discount = true;
                    } else {
                        orderline.is_pwd_line_discount = true;
                    }
                    orderline.apply_bir_discount();
                }
            }
            else{
                  orderline.apply_bir_discount();
            }
            return;
        }
        // AUTO-APPLY LOGIC: Check if special discount mode is active
        if (this.specialDiscountModeEnabled && this.activeDiscountType) {
            const discountConfig = this.pos.getDiscountConfig(this.activeDiscountType);
            const selectedProduct = orderline?.product;
            const allowedTypesPwd = selectedProduct?.is_pwd;
            const allowedTypesSc = selectedProduct?.is_sc;
            const allowedTypesBnpc = selectedProduct?.is_bnpc;
            const allowedTypesMv = selectedProduct?.is_medal;
            const allowedTypesNaac = selectedProduct?.is_naac;
            const allowedTypesSolo = selectedProduct?.is_apic;


            const customerType = this.get_partner()?.senior_pwd_person;

             const supportedDiscounts = [];
            if (allowedTypesPwd) supportedDiscounts.push('pwd');
            if (allowedTypesSc) supportedDiscounts.push('senior');
            if (allowedTypesBnpc) supportedDiscounts.push('bnpc');
            if (allowedTypesNaac) supportedDiscounts.push('naac');
            if (allowedTypesMv) supportedDiscounts.push('medal');
            if (allowedTypesSolo) supportedDiscounts.push('spic');

            if(supportedDiscounts.includes(this.activeDiscountType) ){
                if (discountConfig ) {
                    console.log(`[Auto-Apply] Applying ${discountConfig.name} to new line`);
                    orderline.applyDiscountFromConfig(discountConfig);
                }
            }
        }
    },
});
