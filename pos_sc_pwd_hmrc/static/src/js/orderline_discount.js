/** @odoo-module **/

import { Orderline } from "@point_of_sale/app/store/models";
import { patch } from "@web/core/utils/patch";
import { DiscountCalculator } from "./discount_calculator";

patch(Orderline.prototype, {

    setup() {
        super.setup(...arguments);
        this._specialDiscountLocked = false;
        this.discountConfig = null;
        this.appliedDiscountConfig = null;
        this.applied_discount_id = false;
        this.applied_discount_name = false;
        this.applied_discount_code = false;
    },

    /**
     * Apply discount from configuration (replaces apply_bir_discount and apply_basic_necessity_discount)
     *
     * @param {Object} discountConfig - Discount configuration from pos.special.discount
     */
    applyDiscountFromConfig(discountConfig) {

        if (!discountConfig) {
            console.error('No discount config provided');
            return;
        }
        this.discountConfig = discountConfig;
        this.appliedDiscountConfig = discountConfig;

        if (!this.applied_discount_id){
        this.applied_discount_id = discountConfig.id || false;}

        this.applied_discount_name = discountConfig.name || false;
        this.applied_on_line_text = discountConfig.on_line_text || discountConfig.name || false;
        this.applied_discount_code = discountConfig.discount_code || false;

        try {
            const result = DiscountCalculator.calculate(
                discountConfig,
                this,
                this.quantity
            );

            this.is_sc_line = true;
            this.discount_amount = result.discountAmount;
            this.vat_removed_amount = result.vatRemovedAmount || 0;

            if (result.isBnpcDiscount) {
                this.is_sc_bnpc_discount = true;
                this.is_sc_bnpc_discount_amount = result.discountAmount;
                this.net_vatable_sales = result.netVatableSales || 0;
                this.vat_amount_output = result.vatAmountOutput || 0;
                this.total_amount_due = result.totalAmountDue || 0;
                this.vat_reapplied = result.vatReapplied || 0;

            } else {
                this.is_sc_bnpc_discount = false;

                const discountCode = discountConfig.discount_code;
                this.is_sc_line_discount = discountCode === 'senior';
                this.is_pwd_line_discount = discountCode === 'pwd';

                if (discountConfig.vat_treatment === 'vat_inclusive_reapply') {
                    this.vat_reapplied = result.vatReapplied || 0;
                    this.net_vatable_sales = result.netVatableSales || 0;
                } else {
                     this.vat_reapplied = 0;
                     this.net_vatable_sales = 0;
                }
                const taxes = this._getProductTaxesAfterFiscalPosition() || [];
                this.vat_removeds = taxes.map(t => t.name);
            }

            this.set_discount(discountConfig.discount_rate);

            this.appliedDiscountConfig = discountConfig;

        } catch (error) {
            console.error('Error applying discount:', error);
        }
    },

    /**
     * DEPRECATED: Remove in future version
     * Kept for backward compatibility during migration
     */
    apply_basic_necessity_discount() {
        console.warn('apply_basic_necessity_discount is deprecated. Use applyDiscountFromConfig instead.');

        // Fallback to BNPC config if available
        const bnpcConfig = this.pos.getDiscountConfig('bnpc');
        if (bnpcConfig) {
            this.applyDiscountFromConfig(bnpcConfig);
        } else {
            // Legacy hardcoded logic (to be removed after migration)
            this.is_sc_bnpc_discount_amount = (this.getBasePrice().originalPrice * 0.05) * this.quantity;
            let wo_vat_amount = this.getBasePrice().basePrice * this.quantity;
            const totalRate = this._getProductTaxesAfterFiscalPosition()
                .reduce((sum, t) => sum + t.amount, 0);
            const vatFactor = 1 + (totalRate / 100);
            this.net_vatable_sales = wo_vat_amount - (this.is_sc_bnpc_discount_amount / vatFactor);
            this.vat_amount_output = vatFactor * this.net_vatable_sales;
            this.total_amount_due = this.net_vatable_sales + this.vat_amount_output;
            this.is_sc_bnpc_discount = true;
            this.is_sc_line = true;
            this.set_discount(5);
        }
    },


    set_discount(val) {
        if (this._specialDiscountLocked) {
            console.warn(
                `Cannot apply regular discount — special discount (${this.appliedDiscountConfig?.name || 'special'}) is already applied.`
            );
            return;
        }
        return super.set_discount(...arguments);
    },

    /**
     * Override set_quantity to recalculate discount
     */
    set_quantity(quantity, keep_price) {
        const res = super.set_quantity(...arguments);

        // Recalculate discount if applied
        if (this.is_sc_line && this.appliedDiscountConfig) {
            this.applyDiscountFromConfig(this.appliedDiscountConfig);
        } else if (this.is_sc_line) {
            // Legacy path - will be removed after migration
            this.apply_bir_discount();
        } else if (this.is_sc_bnpc_discount) {
            this.apply_basic_necessity_discount();
        }

        return res;
    },

     setDiscountConfig(config) {

        this.discountConfig = config;
    },

    removeDiscountFromLine() {
        this.is_sc_line = false;
        this.is_sc_bnpc_discount = false;
        this.is_sc_line_discount = false;
        this.is_pwd_line_discount = false;
        this.discount_amount = 0;
        this.vat_removed_amount = 0;
        this.is_sc_bnpc_discount_amount = 0;
        this.net_vatable_sales = 0;
        this.vat_removeds = [];
        this.appliedDiscountConfig = null;
        this.applied_discount_id = false;
        this.applied_discount_name = false;
        this.applied_discount_code = false;
        this.discountConfig = null;
        this.set_discount(0);
    },


    _getVatTreatment() {

        if (
            this.appliedDiscountConfig &&
            this.appliedDiscountConfig.vat_treatment
        ) {

            return this.appliedDiscountConfig.vat_treatment;
        }

        if (
            this.order &&
            (this.order.server_id || this.order.finalized)
        ) {

            return this.discount_vat_treatment || 'vat_inclusive';
        }

        if (
            this.order &&
            this.order.fiscal_position &&
            this.order.fiscal_position.is_zero_exemption_vat
        ) {

            return this.order.fiscal_position
                .is_zero_exemption_vat;
        }

        if (this.product && this.product.taxes_id) {

            if (this.product.taxes_id.includes(3)) {
                return 'zero_rated';
            }

            if (this.product.taxes_id.includes(2)) {
                return 'vat_exempt';
            }
        }

        return 'vat_inclusive';
    },

    /**
     * Update getDisplayData to include discount config info
     */
    getDisplayData() {
        const result = super.getDisplayData();
        Object.assign(result, {
            applied_discount_id: this.applied_discount_id || false,
            applied_discount_name: this.applied_discount_name || (this.appliedDiscountConfig ? this.appliedDiscountConfig.name : false),
            applied_on_line_text: this.applied_on_line_text || (this.appliedDiscountConfig ? (this.appliedDiscountConfig.on_line_text || this.appliedDiscountConfig.name) : false),
            appliedDiscountText: this.applied_on_line_text || this.applied_discount_name || (this.appliedDiscountConfig ? (this.appliedDiscountConfig.on_line_text || this.appliedDiscountConfig.name) : false),
            discount_vat_treatment: this._getVatTreatment(),
        });

        if (this.appliedDiscountConfig) {
            result.appliedDiscountName = this.appliedDiscountConfig.on_line_text || this.appliedDiscountConfig.name;
        }

        return result;
    },

    /**
     * Export discount config reference
     */
    export_as_JSON() {

        const result =
            super.export_as_JSON(...arguments);

        result.applied_discount_id =
            typeof this.applied_discount_id === 'object' && this.applied_discount_id !== null
                ? this.applied_discount_id.id
                : (this.applied_discount_id || false);

        result.applied_discount_name =
            this.applied_discount_name || (this.appliedDiscountConfig ? this.appliedDiscountConfig.name : false);

        result.applied_on_line_text =
            this.applied_on_line_text || (this.appliedDiscountConfig ? (this.appliedDiscountConfig.on_line_text || this.appliedDiscountConfig.name) : false);

        result.applied_discount_code =
            this.discountConfig?.discount_code ||
            this.applied_discount_code ||
            false;

        result.discount_vat_treatment = this._getVatTreatment();

        result.is_sc_line = this.is_sc_line || false;
        result.discount_amount = this.discount_amount || 0;
        result.vat_removed_amount = this.vat_removed_amount || 0;
        result.is_sc_bnpc_discount = this.is_sc_bnpc_discount || false;
        result.is_sc_bnpc_discount_amount = this.is_sc_bnpc_discount_amount || 0;
        result.net_vatable_sales = this.net_vatable_sales || 0;
        result.is_sc_line_discount = this.is_sc_line_discount || false;
        result.is_pwd_line_discount = this.is_pwd_line_discount || false;
        result.vat_reapplied = this.vat_reapplied || 0;
        result.vat_amount_output = this.vat_amount_output || 0;
        result.total_amount_due = this.total_amount_due || 0;
        result.vat_removeds = this.vat_removeds || [];

        return result;
    },

    /**
     * Import discount config reference
     */
    init_from_JSON(json) {
        super.init_from_JSON(...arguments);

        this.applied_discount_id = json.applied_discount_id || false;
        this.applied_discount_name = json.applied_discount_name || false;
        this.applied_on_line_text = json.applied_on_line_text || false;
        this.applied_discount_code = json.applied_discount_code || false;
        this.discount_vat_treatment = json.discount_vat_treatment || false;
        this.is_sc_line = json.is_sc_line || false;
        this.discount_amount = json.discount_amount || 0;
        this.vat_removed_amount = json.vat_removed_amount || 0;
        this.is_sc_bnpc_discount = json.is_sc_bnpc_discount || false;
        this.is_sc_bnpc_discount_amount = json.is_sc_bnpc_discount_amount || 0;
        this.net_vatable_sales = json.net_vatable_sales || 0;
        this.is_sc_line_discount = json.is_sc_line_discount || false;
        this.is_pwd_line_discount = json.is_pwd_line_discount || false;
        this.vat_reapplied = json.vat_reapplied || 0;
        this.vat_amount_output = json.vat_amount_output || 0;
        this.total_amount_due = json.total_amount_due || 0;

        if (this.applied_discount_id && this.pos.discountConfigs) {
            const discountConfig = this.pos.discountConfigs.find(c => c.id === this.applied_discount_id);
            if (discountConfig) {
                this.appliedDiscountConfig = discountConfig;
                this.discountConfig = discountConfig;
            }
        }
    },
});
