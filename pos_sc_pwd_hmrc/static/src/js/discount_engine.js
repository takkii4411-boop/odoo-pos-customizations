/** @odoo-module **/

import { PosStore } from "@point_of_sale/app/store/pos_store";
import { patch } from "@web/core/utils/patch";

patch(PosStore.prototype, {
    async _processData(loadedData) {
        await super._processData(...arguments);

        // Load special discount configurations
        this.discountConfigs = loadedData['pos.special.discount'] || [];
        this.discountConfigsByCode = {};

        // Index configs by discount_code for O(1) lookup
        this.discountConfigs.forEach(config => {
            this.discountConfigsByCode[config.discount_code] = config;
            if (config.on_line_text) {
                // this.discountConfigsByOnLineText[config.on_line_text] = config;
            }
        });

        console.log(`[Discount Engine] Loaded ${this.discountConfigs.length} discount configurations`);
    },

    /**
     * Get discount configuration by code
     * @param {string} discountCode - e.g., 'senior', 'pwd', 'naac'
     * @returns {Object|null} Discount config or null
     */
    getDiscountConfig(discountCode) {
        return this.discountConfigsByCode[discountCode] || null;
    },

    getDiscountConfigByOnLineText(onLineText) {
        return this.discountConfigsByOnLineText[onLineText] || null;
    },
});
