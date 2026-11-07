/** @odoo-module **/

import { Component } from "@odoo/owl";
import { usePos } from "@point_of_sale/app/store/pos_hook";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { ErrorPopup } from "@point_of_sale/app/errors/popups/error_popup";

export class SpecialDiscountButtons extends Component {
    static template = "pos_sc_pwd_hmrc.SpecialDiscountButtons";

    static props = {
        selectedLine: { type: Object, optional: true },
    };

    setup() {
        this.pos = usePos();
        this.popup = useService("popup");
    }

    get discountConfigs() {
        return this.pos.discountConfigs || [];
    }

    get currentOrder() {
        return this.pos.get_order();
    }

    get partner() {
        return this.currentOrder?.get_partner();
    }

    /**
     * Check if special discount mode is enabled for current order
     */
    get isSpecialDiscountModeEnabled() {
        return this.currentOrder?.specialDiscountModeEnabled || false;
    }

    /**
     * Check if component should be visible
     * Only show when:
     * 1. Special discount mode is enabled
     * 2. Customer is selected
     */
    get shouldShowButtons() {
        return this.isSpecialDiscountModeEnabled &&
               this.partner;
    }

    /**
     * Check if a specific discount button should be VISIBLE
     * RULE: All discount buttons show when special discount mode enabled and customer selected
     * Product support check happens at click time (canApplyDiscountToProduct)
     */
    shouldShowDiscountButton(discountConfig) {
        // All discounts visible when mode enabled and customer selected
        // Enabled/disabled state controlled by isButtonEnabled
        return true;
    }


    isButtonEnabled(discountConfig) {
        if (!this.partner) return false;
        if (!this.props || !this.props.selectedLine) return false;

        const customerType = this.partner.senior_pwd_person;
        const discountCode = discountConfig.discount_code;

        if (customerType === false) {
            return discountConfig.is_default_discount === false;
        }

        const primaryCodes = this._getAddonPrimaryCodes(discountCode);
        if (primaryCodes.length > 0) {
            return primaryCodes.includes(customerType);
        }

        return customerType === discountCode;
    }


    canApplyDiscountToProduct(discountConfig) {
        if (!this.props?.selectedLine?.product) return false;
        const product = this.props.selectedLine.product;
        const discountCode = discountConfig.discount_code;

        const supportedCodes = this._getProductSupportedCodes(product);

        if (supportedCodes.length === 0) {
            return false;
        }

        return supportedCodes.includes(discountCode);
    }

    _getProductSupportedCodes(product) {
        const codes = new Set();

        if (product.supported_discount_codes) {
            product.supported_discount_codes.split(',').forEach(code => {
                if (code.trim()) codes.add(code.trim());
            });
        }

        return Array.from(codes);
    }


    _getAddonPrimaryCodes(addonCode) {
        if (addonCode === 'bnpc') {
            return ['senior', 'pwd'];
        }

        const config = this.discountConfigs.find(c => c.discount_code === addonCode);
        if (config?.primary_codes) {
            return config.primary_codes.split(',').map(c => c.trim()).filter(Boolean);
        }

        return [];
    }


    _isCustomerMatchForDiscount(customerType, discountCode) {
        if (customerType === discountCode) return true;

        const primaryCodes = this._getAddonPrimaryCodes(discountCode);
        if (primaryCodes.length > 0) {
            return primaryCodes.includes(customerType);
        }

        return false;
    }




    isButtonActive(discountConfig) {
        return this.props?.selectedLine?.appliedDiscountConfig?.discount_code === discountConfig.discount_code;
    }


    getButtonClass(discountConfig) {
        const baseClass = "btn rounded-1 fw-bolder flex-fill discount-btn";
        const isEnabled = this.isButtonEnabled(discountConfig);
        const isActive = this.isButtonActive(discountConfig);

        if (!isEnabled) {
            return `${baseClass} btn-secondary disabled`;
        }

        return `${baseClass} ${isActive ? 'btn-primary' : 'btn-light'}`;
    }


    async toggleDiscountMode(discountConfig) {

        const order = this.currentOrder;
        const selectedLine = this.props.selectedLine;

        if (!selectedLine || !this.partner) return;

        if (!this.isButtonEnabled(discountConfig)) return;

        const isCurrentlyActive = this.isButtonActive(discountConfig);

        if (isCurrentlyActive) {
            order.activeDiscountType = null;

            if (selectedLine?.is_sc_line &&
                selectedLine.appliedDiscountConfig?.discount_code === discountConfig.discount_code) {
                this.removeDiscountFromLine(selectedLine);
            }
            this.render();
            return;
        }

        if (!this.canApplyDiscountToProduct(discountConfig)) {

            return;
        }

        order.activeDiscountType = discountConfig.discount_code;

        if (selectedLine && !selectedLine.is_sc_line) {
            selectedLine.applyDiscountFromConfig(discountConfig);
        }

        this.render();
    }

    removeDiscountFromLine(line) {
        line.is_sc_line = false;
        line.is_sc_bnpc_discount = false;
        line.is_sc_line_discount = false;
        line.is_pwd_line_discount = false;
        line.discount_amount = 0;
        line.vat_removed_amount = 0;
        line.is_sc_bnpc_discount_amount = 0;
        line.net_vatable_sales = 0;
        line.vat_removeds = [];
        line.appliedDiscountConfig = null;
        line.applied_discount_id = false;
        line.applied_discount_name = false;
        line.applied_discount_code = false;
        line.discountConfig = null;
        line.set_discount(0);
    }
}