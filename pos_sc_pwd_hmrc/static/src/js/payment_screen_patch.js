/** @odoo-module **/

import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { patch } from "@web/core/utils/patch";
import { onMounted } from "@odoo/owl";

patch(PaymentScreen.prototype, {
    setup() {
        super.setup(...arguments);
        onMounted(() => {
            const order = this.currentOrder;
            if (
                order &&
                (order.hmrc_is_void_order ||
                    order.hmrc_is_return_order ||
                    order.hmrc_is_refund_order)
            ) {
                this._setOriginalPaymentMethods(order);
            }
        });
    },

    getNumpadButtons() {
        let buttons = super.getNumpadButtons ? super.getNumpadButtons() : [];

        if (!buttons || buttons.length === 0) {
            buttons = [
                { value: '1', text: '1' },
                { value: '2', text: '2' },
                { value: '3', text: '3' },
                { value: '+10', text: '+10' },
                { value: '4', text: '4' },
                { value: '5', text: '5' },
                { value: '6', text: '6' },
                { value: '+20', text: '+20' },
                { value: '7', text: '7' },
                { value: '8', text: '8' },
                { value: '9', text: '9' },
                { value: '+50', text: '+50' },
                { value: '+/-', text: '+/-' },
                { value: '0', text: '0' },
                { value: '.', text: '.' },
                { value: '⌫', text: '⌫' },
            ];
        }

        const buttonsToHide = ['-', '+10', '+20', '+50'];
        const filtered = buttons.filter(btn => {
            const value = String(btn.value || btn.text || '').trim();
            return !buttonsToHide.includes(value);
        });

        console.log(' Numpad filtered:', filtered.map(b => b.value));
        return filtered;
    },

    _setOriginalPaymentMethods(order) {
    if (order.get_paymentlines().length > 0) return;


    if (order.original_payment_method_id) {
        const paymentMethod = this.pos.payment_methods.find(
            (pm) => pm.id === order.original_payment_method_id
        );
        if (paymentMethod) {
            order.add_paymentline(paymentMethod);
            const newLine = order.get_paymentlines().at(-1);
            if (newLine) {
                newLine.set_amount(order.get_total_with_tax());
            }
            return;
        }
    }


    const allOrders = this.pos.get_order_list();
    const refundedLine = order.get_orderlines().find((l) => l.refunded_orderline_id);
    let originalOrder = null;

    if (refundedLine) {
        originalOrder = allOrders.find((o) =>
            o.get_orderlines().some((l) => l.id === refundedLine.refunded_orderline_id)
        );
    }

    if (originalOrder) {
        const originalPaymentLines = originalOrder.get_paymentlines();
        for (const line of originalPaymentLines) {
            const paymentMethod = this.pos.payment_methods.find(
                (pm) => pm.id === line.payment_method.id
            );
            if (paymentMethod) {
                const refundAmount = -Math.abs(line.get_amount());
                order.add_paymentline(paymentMethod);
                const newLine = order.get_paymentlines().at(-1);
                if (newLine) {
                    newLine.set_amount(refundAmount);
                }
            }
        }
        return;
    }


    const defaultPM = this.pos.payment_methods[0];
    if (defaultPM) {
        order.add_paymentline(defaultPM);
        const newLine = order.get_paymentlines().at(-1);
        if (newLine) {
            newLine.set_amount(order.get_total_with_tax());
        }
    }
},

    get isLocked() {
        const order = this.currentOrder;
        return (
            order &&
            (order.hmrc_is_void_order ||
                order.hmrc_is_return_order ||
                order.hmrc_is_refund_order)
        );
    },

    async validateOrder(force_validation) {
        if (this.isLocked) {
            return super.validateOrder(true);
        }
        return super.validateOrder(...arguments);
    },

    addNewPaymentLine(paymentMethod) {
        if (this.isLocked) return false;
        return super.addNewPaymentLine(...arguments);
    },

    deletePaymentLine(uuid) {
        if (this.isLocked) return;
        return super.deletePaymentLine(...arguments);
    },
});