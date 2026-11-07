/** @odoo-module **/

/**
 * Centralized Discount Calculation Engine
 * Replaces hardcoded 0.05, 0.2 discount logic with database-driven configuration
 */
export class DiscountCalculator {

    /**
     * Calculate discount for an orderline based on discount configuration
     *
     * @param {Object} discountConfig - Discount configuration from pos.special.discount
     * @param {Object} orderline - POS orderline object
     * @param {number} quantity - Quantity to apply discount to
     * @returns {Object} Calculation results
     */
    static calculate(discountConfig, orderline, quantity) {
        if (!discountConfig || !orderline) {
            throw new Error('Invalid discount config or orderline');
        }

        const product = orderline.product;
        const discountRate = discountConfig.discount_rate / 100; // Convert % to decimal
        const fiscalPositionId = discountConfig.fiscal_position_id?.[0]; // Many2one field

        // Get base price breakdown
        const priceBreakdown = orderline.getBasePrice();
        const basePrice = priceBreakdown.basePrice;
        const taxAmount = priceBreakdown.taxAmount;
        const totalRate = priceBreakdown.totalRate;
        const originalPrice = priceBreakdown.originalPrice;

        // Determine if this is a basic necessity product (BNPC discount)
        const isBasicNecessity = discountConfig.discount_code === 'bnpc' || false;

        // Calculate based on fiscal position (VAT treatment)
        let result = {
            discountAmount: 0,
            vatRemovedAmount: 0,
            netVatableSales: 0,
            isBnpcDiscount: isBasicNecessity,
            discountConfig: discountConfig,
        };

//        if (isBasicNecessity) {
//            // BNPC Discount (5% on basic necessities with VAT-inclusive pricing)
//            const bnpcDiscountAmount = originalPrice * discountRate * quantity;
//            const vatFactor = 1 + (totalRate / 100);
//            const woVatAmount = basePrice * quantity;
//            const netVatableSales = woVatAmount - (bnpcDiscountAmount / vatFactor);
//
//            result.discountAmount = bnpcDiscountAmount;
//            result.netVatableSales = netVatableSales;
//            result.vatAmountOutput = vatFactor * netVatableSales;
//            result.totalAmountDue = netVatableSales + result.vatAmountOutput;
//            result.isBnpcDiscount = true;
//
//        } else {
            // Check VAT treatment from discount config
            const vatTreatment = discountConfig.vat_treatment || 'vat_exempt';

            if (vatTreatment === 'vat_inclusive_reapply') {

                result.vatRemovedAmount = quantity * taxAmount;

                result.discountAmount = basePrice * discountRate * quantity;

                const vatOnOriginal = (basePrice * totalRate / 100) * quantity;
                result.vatReapplied = 0;
                result.netVatableSales = (basePrice * quantity) - result.discountAmount;
                result.vatAmountOutput = 0;

//                result.totalAmountDue = result.netVatableSales + vatOnOriginal;
                result.totalAmountDue = result.netVatableSales;

            } else if (vatTreatment === 'vat_exempt') {

                result.vatRemovedAmount = quantity * taxAmount;

                result.discountAmount = basePrice * discountRate * quantity;

                result.vatOnOriginal = 0;

                result.totalAmountDue = (basePrice * quantity) - result.discountAmount;

            } else if (vatTreatment === 'zero_rated') {

                result.vatRemovedAmount = quantity * taxAmount;

                result.discountAmount = basePrice * discountRate * quantity;

                result.totalAmountDue = (basePrice * quantity) - result.discountAmount;

            }  else if (vatTreatment === 'vat_inclusive') {

                  result.vatRemovedAmount = quantity * taxAmount;

                  result.discountAmount = originalPrice * discountRate * quantity;

                  result.totalAmountDue = originalPrice - result.discountAmount;
                  result['priceWithTax'] = result.totalAmountDue
                  result.discountConfig = discountConfig
            }

        return result;
    }

    static validateApplication(discountConfig, orderline, partner) {

        if (orderline.is_sc_line) {
            return {
                valid: false,
                reason: 'Line already has a special discount applied'
            };
        }

        // Check if line is from refund (auto-apply scenario)
        if (orderline.refunded_orderline_id) {
            return { valid: true, reason: '' };
        }

        // Check if customer is eligible
        if (!partner || !partner.is_senior_person) {
            return {
                valid: false,
                reason: 'Customer is not eligible for special discounts'
            };
        }

        // Check if customer discount type matches
        const customerDiscountType = partner.senior_pwd_person;
        if (customerDiscountType && customerDiscountType !== discountConfig.discount_code) {
            // Allow mismatch but warn (admin might manually apply different discount)
            console.warn(`Customer discount type (${customerDiscountType}) does not match discount code (${discountConfig.discount_code})`);
        }

        return { valid: true, reason: '' };
    }
}
