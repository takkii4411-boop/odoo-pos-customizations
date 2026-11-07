/** @odoo-module **/

import { Order, Orderline } from "@point_of_sale/app/store/models";

// Persistent cache for HMRC discount codes — survives reactive resets and order reloads
const _discountCodeCache = new Map();
import { patch } from "@web/core/utils/patch";
import { ConfirmPopup } from "@point_of_sale/app/utils/confirm_popup/confirm_popup";
import { _t } from "@web/core/l10n/translation";
import { PosStore } from "@point_of_sale/app/store/pos_store";
import { ClosePosPopup } from "@point_of_sale/app/navbar/closing_popup/closing_popup";
import { PartnerDetailsEdit } from "@point_of_sale/app/screens/partner_list/partner_editor/partner_editor";
import { PartnerListScreen } from "@point_of_sale/app/screens/partner_list/partner_list";
import {
    roundPrecision as round_pr,
} from "@web/core/utils/numbers";
import { ReprintReceiptScreen } from "@point_of_sale/app/screens/receipt_screen/reprint_receipt_screen";
import { onWillUnmount } from "@odoo/owl";
import { TextAreaPopup } from "@point_of_sale/app/utils/input_popups/textarea_popup";
import { useService } from "@web/core/utils/hooks";
import { TicketScreen } from "@point_of_sale/app/screens/ticket_screen/ticket_screen";
import { ErrorPopup } from "@point_of_sale/app/errors/popups/error_popup";
import { SelectionPopup } from "@point_of_sale/app/utils/input_popups/selection_popup";
import { NumberPopup } from "@point_of_sale/app/utils/input_popups/number_popup";
import {
    formatDateTime,
    deserializeDateTime,
    serializeDateTime,
} from "@web/core/l10n/dates";
import { ActionpadWidget } from "@point_of_sale/app/screens/product_screen/action_pad/action_pad";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
import { ReceiptScreen } from "@point_of_sale/app/screens/receipt_screen/receipt_screen";
import { onMounted } from "@odoo/owl";


patch(ProductScreen.prototype, {
    getNumpadButtons(){
        let res = super.getNumpadButtons()
        if(this.currentOrder._isRefundOrder()){
            for(let val of res){
                val["disabled"]  = true
                this.pos.numpadMode = "";
            }
        }
        return res;
    },

    onMounted(){
        super.onMounted();
        var targets = $("#owl-demo")
            .find("button:contains('Customer Note')," +
                "button:contains('Order List')," +
                "button:contains('Remove Discount')," +
                "button:contains('Global Discount')," +
                "button:contains('Change UOM')," +
                "div:contains('VAT Registered')");
        if(this.currentOrder._isRefundOrder()){
            targets.prop("disabled", true).css("opacity", "0.5");
        }
    },

});

patch(ActionpadWidget.prototype, {
    get isCustomerChangeDisabled() {
        const order = this.currentOrder;

        if (order && (
            order.hmrc_is_void_order ||
            order.hmrc_is_return_order ||
            order.hmrc_is_refund_order
        )) {
            return true;
        }

        if (this.props.actionType === 'refund') {
            return true;
        }

        return false;
    }
});

patch(TicketScreen.prototype, {

    async getApproval() {
        if (this.pos.config.module_pos_hr) {
            const employeesList = this.pos.employees
                .filter((employee) => employee.role == "manager")
                .map((employee) => {
                    return {
                        id: employee.id,
                        item: employee,
                        label: employee.name,
                        isSelected: false,
                    };
                });
            if (!employeesList.length) {
                await this.popup.add(ErrorPopup, {
                    title: _t("No Cashiers"),
                    body: _t("There are no employees to select as cashier. Please create one."),
                });
                return
            }
            const { confirmed, payload: employee } = await this.popup.add(SelectionPopup, {
                title: _t("Manager's Approval"),
                list: employeesList,
            });

            if (!confirmed || !employee || (employee.pin && !(await this.checkPin(employee)))) {
                return;
            }
            return employee;
        }
    },

    async checkPin(employee) {
        const { confirmed, payload: inputPin } = await this.popup.add(NumberPopup, {
            isPassword: true,
            title: _t("Password?"),
        });

        if (!confirmed) {
            return false;
        }

        if (employee.pin !== Sha1.hash(inputPin)) {
            await this.popup.add(ErrorPopup, {
                title: _t("Incorrect Password"),
                body: _t("Please try again."),
            });
            return false;
        }
        return true;
    },


  async onDoRefund() {
    const order = this.getSelectedOrder();
    const currentOrder = this.pos.get_order();

    if (!order || !currentOrder) return false;

    // BLOCK SECOND REFUND / RETURN / VOID
    const orderlines = order.get_orderlines();

    const alreadyRefunded = orderlines.some(
        (line) =>
            (line.refunded_qty && line.refunded_qty > 0) ||
            line.refunded_orderline_id
    );

    if (alreadyRefunded || order.is_refund_locked) {
        await this.popup.add(ErrorPopup, {
            title: _t("Refund Not Allowed"),
            body: _t(
                "This order already has a refund/return/void. Multiple operations are not allowed."
            ),
        });

        return false;
    }

        const totalSoleItem = this._doesOrderTotalSoleItem(order);
        const totalSelectedQtyRefund = this._selectedQtyToRefund(order);

        if (totalSelectedQtyRefund === 0) {
            await this.popup.add(ErrorPopup, {
                title: _t("No Quantity Selected"),
                body: _t("You haven't selected any quantity to return or refund."),
            });
            return false;
        }

        let approval = null;
        let reasonNote = 'No reason provided';

        if (this.pos.config.module_pos_hr) {
            approval = await this.getApproval();
            if (!approval) return false;
        }

        const { confirmed: reasonConfirmed, payload: rawReason } = await this.popup.add(TextAreaPopup, {
            title: _t("Reason Of Return/Refund"),
            startingValue: '',
            confirmText: _t('Okay'),
        });
        if (!reasonConfirmed) return false;

        reasonNote = (rawReason || '').trim() || 'No reason provided';

        let isVoid = false;
        let isRefund = false;
        let isReturn = false;
        let isPartialReturn = false;
        const remainingQty = this._doesOrderTotalSoleItem(order);

        if (totalSelectedQtyRefund === remainingQty ){
            const { confirmed: typeConfirmed, payload: orderType } = await this.popup.add(SelectionPopup, {
                title: _t("Select"),
                list: [
                    { id: 0, label: 'Refund', item: 'refund', isSelected: true },
                    { id: 1, label: 'Void', item: 'void', isSelected: false },
                ],
            });

            if (!typeConfirmed) return false;

            if (orderType === 'void') {
                const today_date = luxon.DateTime.now().toISODate();
                const orderDateStr = luxon.DateTime.fromISO(order.date_order).toISODate();

                if (today_date !== orderDateStr) {
                    this.popup.add(ErrorPopup, {
                        title: _t("Same Day Void Restriction"),
                        body: _t("Only same-day orders can be voided."),
                    });
                    return false;
                }
                isVoid = true;
            } else if (orderType === 'refund'){

            const today = luxon.DateTime.now();
            const orderDate = luxon.DateTime.fromISO(order.date_order);
            const diffDays = today.startOf('day').diff(orderDate.startOf('day'), 'days').days;

                if (diffDays > 7) {
                        this.popup.add(ErrorPopup, {
                        title: _t("Refund Restriction"),
                        body: _t("Refund is only allowed within 7 days from the transaction date."),
                    });
                    return false;
                }
         isRefund = true;
            } else {

            const today = luxon.DateTime.now();
            const orderDate = luxon.DateTime.fromISO(order.date_order);
            const diffDays = today.startOf('day').diff(orderDate.startOf('day'), 'days').days;

                if (diffDays > 7) {
                        this.popup.add(ErrorPopup, {
                        title: _t("Refund Restriction"),
                        body: _t("Refund is only allowed within 7 days from the transaction date."),
                    });
                    return false;
                }
         isRefund = true;
            }
        } else {
            const today = luxon.DateTime.now();
            const orderDate = luxon.DateTime.fromISO(order.date_order);
            const diffDays = today.startOf('day').diff(orderDate.startOf('day'), 'days').days;

                if (diffDays > 7) {
                        this.popup.add(ErrorPopup, {
                        title: _t("Return Restriction"),
                        body: _t("Return is only allowed within 7 days from the transaction date."),
                    });
                    return false;
                }

        isReturn = true;
        }



        let result = await super.onDoRefund(...arguments);

        const newRefundOrder = this.pos.get_order();
        newRefundOrder.is_refund_locked = true;
        order.is_refund_locked = true;
        if (!newRefundOrder) {
            console.warn("Refund order not created.");
            return result;
            }

        if (newRefundOrder) {
            newRefundOrder.hmrc_is_void_order = isVoid;
            newRefundOrder.hmrc_is_refund_order = isRefund;
            newRefundOrder.hmrc_is_return_order = isReturn;
            newRefundOrder.return_reason_message = reasonNote;
            const actionLabel =
                newRefundOrder.hmrc_is_void_order ? 'Void'
                : newRefundOrder.hmrc_is_refund_order ? 'Refund'
                : newRefundOrder.hmrc_is_return_order ? 'Return'
                : 'Sale';
            const htmlMessage = `
                <div>
                    <i class="fa fa-info-circle ms-2"></i>
                    <strong>${actionLabel} By <em>${this.pos.cashier?.name || 'Unknown'}</em></strong><br/>
                    ${approval ? `<strong>Approver: <em>${approval?.name || 'Unknown'}</em></strong><br/>` : ''}
                    <span>Date & Time: <em>${formatDateTime(luxon.DateTime.now())}</em></span><br/>
                    <span>Session: <em>${this.pos.pos_session?.name || 'Unknown'}</em></span><br/>
                    <span>Reason:</span> <em>${reasonNote}</em>
                </div>
            `;
            newRefundOrder.return_message = htmlMessage;

            if (order.invoice_number) {
                newRefundOrder.original_inv_ref = order.invoice_number;
            }
            newRefundOrder.ref_order_date = order.date_order;

            const originalPaymentLines = order.get_paymentlines();
            if (originalPaymentLines && originalPaymentLines.length > 0) {
                newRefundOrder.original_payment_method_id = originalPaymentLines[0].payment_method.id;
            }

            if(order.fiscal_position){
                newRefundOrder.set_fiscal_position(order.fiscal_position);
            }

            // Copy partner from original order so discount checks work
            const originalPartner = order.get_partner();
            if (originalPartner) {
                newRefundOrder.set_partner(originalPartner);
                console.log('onDoRefund: partner set on refund order →', originalPartner.name, originalPartner.senior_pwd_person);
            }
        }

        return result;
    },

    _selectedQtyToRefund(order) {
    if (!order) return 0;

    return order.get_orderlines().reduce((total, l) => {
        const qty = this.pos.toRefundLines?.[l.id]?.qty || 0;
        return total + Math.abs(qty);
    }, 0);
    },
    _doesOrderTotalSoleItem(order) {
        const orderlines = order.get_orderlines();
        const refundedQty = orderlines.reduce((total_refund, crr) => total_refund + (crr.refunded_qty || 0), 0);
        const totalQty = orderlines.reduce((total_refund, crr) => total_refund + crr.get_quantity(), 0);
        return totalQty - refundedQty;
    },

    _getToRefundDetail(orderline) {
        let refundDetail = super._getToRefundDetail(...arguments);
        refundDetail.orderline['is_sc_line'] = orderline.is_sc_line;
//        refundDetail.orderline['vat_reapplied'] = orderline.vat_reapplied;
        // refundDetail.orderline['discount_amount'] = orderline.discount_amount;
        // refundDetail.orderline['vat_removed_amount'] = orderline.vat_removed_amount;
        refundDetail.orderline['is_sc_bnpc_discount'] = orderline.is_sc_bnpc_discount;
        // refundDetail.orderline['is_sc_bnpc_discount_amount'] = orderline.is_sc_bnpc_discount_amount;
        // refundDetail.orderline['net_vatable_sales'] = orderline.net_vatable_sales;
        refundDetail.orderline['is_sc_line_discount'] = orderline.is_sc_line_discount;
        refundDetail.orderline['is_pwd_line_discount'] = orderline.is_pwd_line_discount;
        refundDetail.orderline['discount_vat_treatment'] = orderline.discount_vat_treatment;
        refundDetail.orderline['appliedDiscountConfig'] = orderline.appliedDiscountConfig;
         refundDetail.orderline['applied_discount_id'] = orderline.applied_discount_id;
        refundDetail.orderline['applied_discount_name'] = orderline.applied_discount_name;
        // Use multiple fallback sources — property might get cleared between init_from_JSON and here
        const cacheVal = _discountCodeCache.get(orderline.id);
        const exported = orderline.export_as_JSON ? orderline.export_as_JSON() : {};
        refundDetail.orderline['applied_discount_code'] = 
            orderline.applied_discount_code || 
            orderline.appliedDiscountConfig?.discount_code || 
            exported.applied_discount_code || 
            cacheVal ||
            false;
        return refundDetail;
    },
    _prepareRefundOrderlineOptions(toRefundDetail) {
        let options = super._prepareRefundOrderlineOptions(...arguments);
        const { qty, orderline } = toRefundDetail;
        options['is_sc_line'] = orderline.is_sc_line;
//        options['vat_reapplied'] = orderline.vat_reapplied;
        // options['discount_amount'] = orderline.discount_amount;
        // options['vat_removed_amount'] = orderline.vat_removed_amount;
        options['is_sc_bnpc_discount'] = orderline.is_sc_bnpc_discount;
        // options['is_sc_bnpc_discount_amount'] = orderline.is_sc_bnpc_discount_amount;
        // options['net_vatable_sales'] = orderline.net_vatable_sales;
        options['is_sc_line_discount'] = orderline.is_sc_line_discount;
        options['is_pwd_line_discount'] = orderline.is_pwd_line_discount;
        options['discount_vat_treatment'] = orderline.discount_vat_treatment;
        options['appliedDiscountConfig'] = orderline.appliedDiscountConfig;
        options['applied_discount_id'] = orderline.applied_discount_id;
        options['applied_discount_name'] = orderline.applied_discount_name;
        options['applied_discount_code'] = orderline.applied_discount_code;

        return options;
    }
})
patch(Order.prototype, {

    add_product(product, options) {

        if (this.is_refund_locked ||
            this.hmrc_is_void_order ||
            this.hmrc_is_return_order ||
            this.hmrc_is_refund_order) {
            this.env.services.popup.add(ErrorPopup, {
                title: "Not Allowed",
                body: "You cannot add new items in a refund order.",
            });
            return;
        }

        return super.add_product(...arguments);
    },

    set_fiscal_position(fiscal_position) {

        if (this._isRefundOrder() && this.fiscal_position?.id !== fiscal_position?.id) {
            this.env.services.popup.add(ErrorPopup, {
                title: "Not Allowed",
                body: "Fiscal Position cannot be changed in Return/Refund order.",
            });
            return;
        }

        return super.set_fiscal_position(...arguments);
    }

});

patch(ReprintReceiptScreen.prototype, {
    setup() {
        super.setup();
        this.popup = useService("popup");

        const currentOrder = this.pos.get_order();

        this.originalFiscalPosition = currentOrder.fiscal_position;

        const reprintOrderFiscalPosition = this.props.order.fiscal_position;

        if (reprintOrderFiscalPosition) {
            currentOrder.set_fiscal_position(reprintOrderFiscalPosition);
        }

        onWillUnmount(() => {
            const order = this.pos.get_order();
            if (order) {
                order.set_fiscal_position(this.originalFiscalPosition);
            }
        });
    },
    async tryReprint() {
        let { confirmed, payload: inputNote } = await this.popup.add(TextAreaPopup, {
            startingValue: '',
            title: _t("Reason for Reprinting"),
            confirmText: _t('Print'),
        });

        if (confirmed) {
            inputNote = inputNote != '' ? inputNote.trim() : 'No reason provided';
            const htmlMessage = `
                <div>
                    <i class="fa fa-print ms-2"></i>
                    <strong>Receipt Reprinted By <em>${this.pos.get_cashier()?.name || 'Unknown'}</em></strong><br/>
                    <span>Date & Time: <em>${formatDateTime(luxon.DateTime.now())}</em></span><br/>
                    <span>Session: <em>${this.pos.pos_session?.name || 'Unknown'}</em></span><br/>
                    <span>Invoice Number: <em>${this.props.order?.invoice_number || 'Unknown'}</em></span><br/>
                    <span>Reason:</span> <em>${inputNote}</em>
                </div>
            `;

            await this.env.services.orm.call(
                "pos.order",
                "message_post",
                [[this.props.order.server_id]],
                { body: htmlMessage, flag: true, reprint:{ reason: inputNote, reprint_by: this.pos.get_cashier()?.name || 'Unknown' , date: formatDateTime(luxon.DateTime.now())} }
            );

            await super.tryReprint(...arguments);
        }
    }

});

patch(PartnerListScreen.prototype, {
    createPartner() {
        const res = super.createPartner(...arguments);
        this.state.editModeProps.partner.is_senior_person = true;
        return res;
    },
});

patch(PartnerDetailsEdit.prototype, {
    setup() {
        const res = super.setup(...arguments);
        this.changes.res_partner_business_style = this.props.partner.res_partner_business_style || '';
        this.changes.is_senior_person = this.props.partner.is_senior_person || '';
        this.changes.senior_pwd_person = this.props.partner.senior_pwd_person || '';
        this.changes.naac_id_no = this.props.partner.naac_id_no || '';
        this.changes.sc_id_no = this.props.partner.sc_id_no || '';
        this.changes.pwd_id_no = this.props.partner.pwd_id_no || '';
        this.changes.medal_id_no = this.props.partner.medal_id_no || '';
        this.changes.spic_id_no = this.props.partner.spic_id_no || '';
        this.changes.spic_child_name = this.props.partner.spic_child_name || '';
        this.changes.spic_child_birth_date = this.props.partner.spic_child_birth_date || false;
        this.changes.spic_child_age = this.props.partner.spic_child_age || 0;
        this.changes.general_id_no = this.props.partner.general_id_no || '';

        if (this.props.partner.spic_child_birth_date) {
            this.changes.spic_child_age = this._calculateAge(this.props.partner.spic_child_birth_date);
        }

        return res;
    },

    _calculateAge(birthDateStr) {
        if (!birthDateStr) return 0;

        const today = new Date();
        const birthDate = new Date(birthDateStr);

        let age = today.getFullYear() - birthDate.getFullYear();
        const monthDiff = today.getMonth() - birthDate.getMonth();

        if (monthDiff < 0 || (monthDiff === 0 && today.getDate() < birthDate.getDate())) {
            age--;
        }

        return age >= 0 ? age : 0;
    },

    onSpicChildBirthDateChange(ev) {
        const selectedDate = ev.target.value;

        this.changes.spic_child_birth_date = selectedDate || false;


        this.changes.spic_child_age = this._calculateAge(selectedDate);
        this.render();
    },


    willSave() {
        const type = this.changes.senior_pwd_person || '';
        const knownTypes = ['senior', 'pwd', 'naac', 'spic', 'medal'];

        this.changes.is_senior_person = false;

        // For known types, clear general_id_no. For new dynamic types, keep it.
        if (knownTypes.includes(type)) {
            this.changes.general_id_no = '';
        }

        this.changes.naac_id_no = type === 'naac' ? this.changes.naac_id_no : '';
        this.changes.sc_id_no = type === 'senior' ? this.changes.sc_id_no : '';
        this.changes.pwd_id_no = type === 'pwd' ? this.changes.pwd_id_no : '';
        this.changes.spic_id_no = type === 'spic' ? this.changes.spic_id_no : '';
        this.changes.medal_id_no = type === 'medal' ? this.changes.medal_id_no : '';

        if (type !== 'spic') {
            this.changes.spic_child_name = '';
            this.changes.spic_child_birth_date = false;
        }

        if (this.changes.spic_child_birth_date) {
            this.changes.spic_child_age = this._calculateAge(this.changes.spic_child_birth_date);
        }

        return super.willSave(...arguments);
    },


});

patch(ClosePosPopup.prototype, {
    async closeSession() {
        const result = await super.closeSession();
        localStorage.removeItem("invoice_number");
        return result;
    }
});

patch(PosStore.prototype, {


   getReceiptHeaderData() {
    let partner = this.get_order().get_partner();
    let order = this.get_order();

    if (this.mainScreen.component.name == "ReprintReceiptScreen") {
        partner = this.mainScreen.props.order.partner;
        order = this.mainScreen.props.order;
    }

    return {
        ...super.getReceiptHeaderData(...arguments),

        partner: partner,
        min_no: this.config.x_min_number,
        x_sr_no: this.config.x_serial_number,
        hide_company_logo: this.config.hide_company_logo,



        invoice_number: order ? order.invoice_number : "",
        return_invoice_number: order ? order.return_invoice_number : "",
        void_invoice_number: order ? order.void_invoice_number : "",
        transaction_number: order ? order.transaction_number : "",
        original_inv_ref: order ? order.original_inv_ref : "",
        is_refund_order: order ? order._isRefundOrder() : false,
        date: order ? order.date_order : "",
        ref_order_date: order ? order.ref_order_date : "",

         is_zero_exemption_vat: order ? order.fiscal_position?.is_zero_exemption_vat : "",
        footer_text: order ? order.fiscal_position?.footer_text : "",
        is_mixed_sale: order ? order.isMixedSale() : false,

        is_reprint_order: order ? (order.isReprintOrder() || order.print_count > 0) : false,
        reprint_datetime: formatDateTime(luxon.DateTime.now()),

    };
},
    async load_server_data() {
        const invoice_number = await this.orm.silent.call(
            "pos.order",
            "get_current_invoice_number",
            []
        );
        const orders = this.get_order_list();
        const sequences = orders.map(order => parseInt(order.invoice_number || "0", 10));
        const serverNum = parseInt(invoice_number || "0", 10);
        const maxNum = Math.max(serverNum, ...(sequences.length ? sequences : [0]));
        this.invoice_number = String(maxNum).padStart(8, "0");
        await super.load_server_data(...arguments);
    },

    async _save_to_server(orders, options) {
        const server_ids = await super._save_to_server(...arguments);
        if (!server_ids?.length) {
            return server_ids;
        }
        const orderIds = server_ids.map(o => o.id);
        try {
            const extraData = await this.orm.searchRead(
                "pos.order",
                [["id", "in", orderIds]],
                ["id", "invoice_number","return_invoice_number","void_invoice_number","transaction_number"]
            );

            const orderMap = new Map(extraData.map(d => [d.id, d.invoice_number]));
            const orderList = this.get_order_list();

            for (const d of extraData) {
                    const order = orderList.find(o => o.server_id === d.id);
                    if (order) {
                        order.invoice_number = d.invoice_number;
                        order.return_invoice_number = d.return_invoice_number;
                        order.void_invoice_number = d.void_invoice_number;
                        order.transaction_number = d.transaction_number; // ADD THIS
                    }
                }
            localStorage.setItem("pos_invoice_numbers", JSON.stringify(Object.fromEntries(orderMap)));

        } catch (error) {
            const savedNumbers = JSON.parse(localStorage.getItem("pos_invoice_numbers") || "{}");
            const orderList = this.get_order_list();

            for (const serverId of orderIds) {
                if (savedNumbers[serverId]) {
                    const order = orderList.find(o => o.server_id === serverId);
                    if (order) {
                        order.invoice_number = savedNumbers[serverId];
                    }
                }
            }
        }
        return server_ids;
    },

    nextInvoiceNumber() {
        let num = parseInt(localStorage.getItem("invoice_number") || (this.invoice_number || "0"), 10);
        num = isNaN(num) ? 0 : num;
        num += 1;
        this.invoice_number = String(num).padStart(8, "0");
        return this.invoice_number;
    },

    add_new_order() {
        const order = super.add_new_order(...arguments);
        if(!order.hmrc_is_void_order && !order.hmrc_is_return_order && !order.hmrc_is_refund_order){
            order.invoice_number = this.nextInvoiceNumber();
            localStorage.setItem("invoice_number", order.invoice_number);
        }
        return order;
    },
});

patch(Order.prototype, {
    setup(_defaultObj, options) {
        super.setup(...arguments);
            if(options?.json){
                this.return_invoice_number = options?.json.return_invoice_number;
                this.void_invoice_number = options?.json.void_invoice_number;
                this.original_inv_ref = options?.json.original_inv_ref;
                this.hmrc_is_void_order = options?.json.hmrc_is_void_order;
                this.hmrc_is_return_order = options?.json.hmrc_is_return_order;
                this.hmrc_is_refund_order = options?.json.hmrc_is_refund_order;
                this.return_message = options?.json.return_message;
                this.return_reason_message = options?.json.return_reason_message;
                this.transaction_number = options?.json.transaction_number || false; // ADD THIS
                this.print_count = 0;
                this.specialDiscountModeEnabled = options?.json.specialDiscountModeEnabled || false;
                this.activeDiscountType = options?.json.activeDiscountType || null;
                this.is_refund_locked = options?.json.is_refund_locked || false;
            }
            else{
                this.return_invoice_number = false;
                this.void_invoice_number = false;
                this.original_inv_ref = false;
                this.hmrc_is_void_order = false;
                this.hmrc_is_return_order = false;
                this.hmrc_is_refund_order = false;
                this.return_message = false;
                this.return_reason_message = false;
                this.transaction_number = false;
                this.specialDiscountModeEnabled = false;
                this.activeDiscountType = null;
                this.is_refund_locked = false;
            }
     },

    export_as_JSON() {
        const json = super.export_as_JSON(...arguments);
        json.invoice_number = this.invoice_number;
        json.vat_sales = this.getVatSales();
        json.receipt_text = this.receipt_text || '';
        json.transaction_number = this.transaction_number;

        json.vat_amount = this.getTotalVat();
        json.vat_exempt_sales = this.totalVatExemption();
        json.zero_rated_sales = this.getZeroRatedSales();
        json.non_vat_sales = this.getNonVatSales();
        json.total_sales = this.getTotalSales();
        json.total_vat = this.getTotalVat();
        json.total_vat_exemption = this.totalVatExemption();
        json.return_invoice_number = this.return_invoice_number;
        json.void_invoice_number = this.void_invoice_number;
        json.original_inv_ref = this.original_inv_ref;
        json.hmrc_is_void_order = this.hmrc_is_void_order;
        json.hmrc_is_return_order = this.hmrc_is_return_order;
        json.hmrc_is_refund_order = this.hmrc_is_refund_order;
        json.is_refund_locked = this.is_refund_locked || false;
        json.return_message = this.return_message;
        json.return_reason_message = this.return_reason_message;
        json.ref_order_date = this.ref_order_date ? serializeDateTime(this.ref_order_date) : false;
        json.specialDiscountModeEnabled = this.specialDiscountModeEnabled || false;
        json.activeDiscountType = this.activeDiscountType || null;
        json.original_payment_method_id = this.original_payment_method_id || false;
        return json;
    },

    init_from_JSON(json) {
        super.init_from_JSON(...arguments);
        this.invoice_number = json.invoice_number;
        this.transaction_number = json.transaction_number || false; // ADD THIS
        this.return_invoice_number = json.return_invoice_number || false;
        this.void_invoice_number = json.void_invoice_number || false;
        this.original_inv_ref = json.original_inv_ref || false;
        this.hmrc_is_void_order = json.hmrc_is_void_order || false;
        this.hmrc_is_return_order = json.hmrc_is_return_order || false;
        this.hmrc_is_refund_order = json.hmrc_is_refund_order || false;
        this.is_refund_locked = json.is_refund_locked || false;
        this.return_message = json.return_message || false;
        this.ref_order_date = json.ref_order_date ? deserializeDateTime(json.ref_order_date) : false;
        this.print_count = json.print_count || 0;
        this.specialDiscountModeEnabled = json.specialDiscountModeEnabled || false;
        this.activeDiscountType = json.activeDiscountType || null;
        this.original_payment_method_id = json.original_payment_method_id || false;
    },


    set_orderline_options(orderline, options) {
        super.set_orderline_options(...arguments);

        if (!options) return;

        const fields = [
            'is_sc_line',
            'discount_amount',
            'vat_reapplied',
            'vat_removed_amount',
            'is_sc_bnpc_discount',
            'is_sc_bnpc_discount_amount',
            'net_vatable_sales',
            'is_sc_line_discount',
            'is_pwd_line_discount',
            'discount_vat_treatment',
            'appliedDiscountConfig',
            'applied_discount_id',
            'applied_discount_name',
            'applied_discount_code',
        ];

        for (const field of fields) {
            if (Object.prototype.hasOwnProperty.call(options, field)) {
                orderline[field] = options[field];
            }
        }
        if (!orderline.applied_discount_id && orderline.appliedDiscountConfig) {
            orderline.applied_discount_id = orderline.appliedDiscountConfig.id;
        }
    },

    getVatSales() {
     if (['zero_rated','vat_exempt'].includes(this.fiscal_position?.is_zero_exemption_vat)) {
       return 0;
   }
    return this.orderlines.reduce((sum, line) => {
        const qty = line.quantity;
        const basePriceInfo = line.getBasePrice();
        const lineNetWithoutTax = line.get_price_without_tax();
        const VatTreatment = line._getVatTreatment();

        if (line.vat_reapplied > 0) {
            return sum + lineNetWithoutTax;
        }


        else if (line.is_sc_bnpc_discount) {
            // zero vat will skip
            if (line.product.taxes_id.includes(3)){
                return sum;
            }

            // vat exempt will skip
            else if (line.product.taxes_id.includes(2)){
                return sum;
            }
            else return sum + lineNetWithoutTax;

        }
         // zero vat will skip
        else if (line.product.taxes_id.includes(3)){
            return sum;
        }

        // vat exempt will skip
        else if (line.product.taxes_id.includes(2)){
            return sum;
        }

        else if (VatTreatment === 'vat_inclusive') {
            return sum + lineNetWithoutTax;
        }
        else if (line.is_sc_line && line.vat_reapplied === 0) {
            return sum;
        }

        return sum + lineNetWithoutTax;

    }, 0);
},

    getNonVatSales() {

    if (this.fiscal_position?.is_zero_exemption_vat === 'zero_rated') {
        return 0;
    }

    if (this.fiscal_position?.is_zero_exemption_vat === 'vat_exempt') {
        return 0;
    }

        let orderLines = this.get_orderlines();

        // if(this.fiscal_position?.is_zero_exemption_vat == 'vat_exempt')
        //     return this.get_total_without_tax();

        return + orderLines.reduce((nonVatSales, line) => {
            if (line.is_sc_line) {
                return nonVatSales + line.discount_amount;
            }
            return nonVatSales;
        }, 0).toFixed(2);
    },

    getTotalSales(){
        return  this.getVatSales() + this.getZeroRatedSales() + this.totalVatExemption();
    },

    getTotalDiscount() {
        let orderLines = this.get_orderlines();
        return +orderLines.reduce((totalDiscount, line) => {
            if (line.discount_amount && line.discount_amount > 0) {
                return totalDiscount + line.discount_amount;
            }

            // BNPC discount
            if (line.is_sc_bnpc_discount_amount && line.is_sc_bnpc_discount_amount > 0) {
                return totalDiscount + line.is_sc_bnpc_discount_amount;
            }

            // Regular discount (non-special lines)
            if (line.get_discount() > 0 && !line.is_sc_line && !line.is_sc_bnpc_discount) {
                const discountAmount = line.get_price_without_tax() * (line.get_discount() / 100);
                return totalDiscount + discountAmount;
            }

            return totalDiscount;
        }, 0).toFixed(2);
    },

//    get_total_tax(){
//        return this.get_orderlines().reduce((total, line) => {
//        if (line.vat_reapplied > 0) {
//            return total + line.vat_reapplied;
//        }
//        return total + line.get_all_prices().tax;
//        }, 0);
//    },

    getTotalVat() {
        return this.orderlines.reduce((total, line) => {
            if (line.vat_reapplied > 0) {
                // NAAC: report FULL original VAT
                return total + line.vat_reapplied;
            }

            if (line.is_sc_line && line.vat_reapplied === 0) {
                // Normal exempt → no VAT
                return total + 0;
            }

            // Normal taxable lines (incl. BNPC after 5% discount)
            const lineRate = line._getProductTaxesAfterFiscalPosition()
                .reduce((sum, t) => sum + t.amount, 0);
            const base = line.get_price_without_tax();
            return total + (base * lineRate / 100);
        }, 0);
    },

    totalVatExemption() {
        if(this.fiscal_position?.is_zero_exemption_vat == 'vat_exempt')
            return this.get_total_without_tax_wo_discount();
        if(this.fiscal_position?.is_zero_exemption_vat == 'zero_rated')
            return 0;
        let orderLines = this.get_orderlines();

        return +orderLines.reduce((totalVat, line) => {
            if (line.get_tax() == 0) {
                if (line.product.taxes_id.includes(3)) {
                    return totalVat;
                }
                return totalVat + (line.getBasePrice().originalPrice * line.quantity || 0) - line.vat_removed_amount;
            }
            return totalVat;
        }, 0).toFixed(2);

        // return +orderLines.reduce((totalVat, line) => {
        //     if (line.is_sc_line || line.get_tax() == 0) {
        //         return totalVat + (line.discount_amount || 0);
        //     }
        //     return totalVat;
        // }, 0).toFixed(2);
    },

    calculateVatExemption() {
        let orderLines = this.get_orderlines();
        return +orderLines.reduce((vatExemptTotal, line) => {
            if (line.is_sc_line) {
                return line.quantity * line.getBasePrice()?.taxAmount;
            }
            return vatExemptTotal;
        }, 0).toFixed(2);
    },

    getZeroRatedSales() {
        if(this.fiscal_position?.is_zero_exemption_vat == 'vat_exempt')
            return 0;
        if(this.fiscal_position?.is_zero_exemption_vat == 'zero_rated')
            return this.get_total_without_tax();
        // Calculate zero-rated sales from products with zero-rated tax (tax ID 3)
        let orderLines = this.get_orderlines();
        return +orderLines.reduce((zeroRatedTotal, line) => {
            if (line.product.taxes_id.includes(3)) {
                return zeroRatedTotal + (line.getBasePrice().originalPrice * line.quantity || 0);
            }
            return zeroRatedTotal;
        }, 0).toFixed(2);

        // let orderLines = this.get_orderlines();
        // return +orderLines.reduce((vatExemptTotal, line) => {

        //     if (line && !line.is_sc_line && !line.get_tax()) {
        //         return line.get_display_price();
        //     }
        //     return vatExemptTotal;
        // }, 0).toFixed(2);
        // return this.get_total_with_tax();

    },

    // NOTE: add_product implementation moved to order_discount.js
    // This centralizes discount logic and removes auto-apply behavior
    // Only manual discount application via buttons is now supported


    get_total_without_tax_wo_discount() {
        return round_pr(
            this.orderlines.reduce(function (sum, orderLine) {
                return sum + orderLine.getBasePrice()?.['originalPrice'] * orderLine.quantity;
            }, 0),
            this.pos.currency.rounding
        );
    },

    getVatTreatmentFromDiscounts() {
        const vatTreatments = new Set();

        for (const line of this.orderlines) {
            if (line.appliedDiscountConfig && line.appliedDiscountConfig.vat_treatment) {
                vatTreatments.add(line.appliedDiscountConfig.vat_treatment);
            }
        }

        return {
            treatments: vatTreatments,
            isMixed: vatTreatments.size > 1,
            hasSingle: vatTreatments.size === 1,
            single: vatTreatments.size === 1 ? Array.from(vatTreatments)[0] : null
        };
    },

    isMixedSale(){
        const discountVatInfo = this.getVatTreatmentFromDiscounts();

        if (discountVatInfo.isMixed) {
            return true;
        }

        if (discountVatInfo.treatments.size > 0) {
            return false;
        }

        let exempt = false;
        let non_exempt = false;
        if(!this.fiscal_position?.is_zero_exemption_vat){
            let exempt_tax_ids = Object.values(this.fiscal_position?.fiscal_position_taxes_by_id || {})
                .map(fp => this.pos.taxes_by_id[fp.tax_dest_id?.[0]].amount == 0 ? fp.tax_dest_id?.[0] : null);
            let non_exempt_tax_ids = Object.values(this.fiscal_position?.fiscal_position_taxes_by_id || {})
                .map(fp => this.pos.taxes_by_id[fp.tax_dest_id?.[0]].amount != 0 ? fp.tax_dest_id?.[0] : null);
            exempt = this.orderlines.filter(l=>{
                return exempt_tax_ids.some(id=>l.product.taxes_id.includes(id))
            })
            non_exempt = this.orderlines.filter(l=>{
                return non_exempt_tax_ids.some(id=>l.product.taxes_id.includes(id))
            });
        }
        return exempt.length > 0 && non_exempt.length > 0;
    },

    isReprintOrder(){
        return this.pos.mainScreen.component.name == "ReprintReceiptScreen";
    },

   export_for_printing() {
        const result = super.export_for_printing(...arguments);

        const partner = this.get_partner();
       let partner_id = "";
       let address = "";
       let discount_code = "";
        if (partner) {
            address = [
                partner.street,
                partner.street2,
                partner.city,
                partner.zip,
                partner.state_id && partner.state_id[1],
                partner.country_id && partner.country_id[1]
            ].filter(Boolean).join(', ');

            if (partner.senior_pwd_person === 'naac') {
                partner_id = partner.naac_id_no;
            } else if (partner.senior_pwd_person === 'senior') {
                partner_id = partner.sc_id_no;
            } else if (partner.senior_pwd_person === 'pwd') {
                partner_id = partner.pwd_id_no;
            } else if (partner.senior_pwd_person === 'spic') {
                partner_id = partner.spic_id_no;
            } else if (partner.senior_pwd_person === 'medal') {
                partner_id = partner.medal_id_no;
            } else {
                partner_id = partner.general_id_no;
            }

            discount_code = partner.discount_code || "";
        }
        result.discount_code = discount_code;
        result.partner_name = partner ? partner.name : "";
        result.partner_address = address || "";
        result.partner_id = partner_id || "";
        result.partner_tin = partner ? partner.vat : "";
        result.res_partner_business_style = partner ? partner.res_partner_business_style : "";

        result.vat_sales = this.getVatSales();
        result.non_vat_sales = this.getNonVatSales();
        result.total_sales = this.getTotalSales();
        result.total_vat = this.getTotalVat();
        result.total_vat_exemption= this.totalVatExemption();
        result.invoice_number = this.invoice_number;
        result.transaction_number = this.transaction_number || "";
        result.zero_rated_sales= this.getZeroRatedSales();

        const discountVatInfo = this.getVatTreatmentFromDiscounts();

        if (discountVatInfo.hasSingle && discountVatInfo.single !== 'vat_inclusive_reapply') {
            result.is_zero_exemption_vat = discountVatInfo.single;
        } else {
            result.is_zero_exemption_vat = this.fiscal_position?.is_zero_exemption_vat;
        }
        result.total_discount = this.getTotalDiscount();
        result.vat_exempt_sales = this.totalVatExemption();
//        result.is_mixed_sale = this.isMixedSale();
        result.is_reprint_order = this.isReprintOrder() || (this.print_count > 0);
        result.reprint_datetime = formatDateTime(luxon.DateTime.now());
        result.is_refund_order = this._isRefundOrder();
        result.return_invoice_number = this.return_invoice_number;
        result.void_invoice_number = this.void_invoice_number;
        result.original_inv_ref = this.original_inv_ref;
        result.ref_order_date = this.ref_order_date ? formatDateTime(this.ref_order_date) : false;
        result.print_count = this.print_count || 0;
        result.fiscal_position_name = this.fiscal_position?.name
        result.footer_text = this.fiscal_position?.footer_text;
        result.paymentlines_array = this.get_paymentlines().map(line => ({
            name: line.payment_method.name,
            amount: line.get_amount(),
        }));
        return result;
    },

   removeOrderline(line) {
        let removeLLine = super.removeOrderline(line);
        const linesToRemove = this.get_orderlines().filter(l => l.refunded_orderline_id);
        if (!linesToRemove?.length) {
            if (this.hmrc_is_void_order) {
                this.hmrc_is_void_order = false;
            }
            if (this.hmrc_is_return_order) {
                this.hmrc_is_return_order = false;
            }
            if (this.hmrc_is_refund_order) {
                this.hmrc_is_refund_order = false;
            }
            if (this.return_message) {
                this.return_message = false;
            }
            if (this.return_reason_message){
                this.return_reason_message = false;
            }
            if (this.return_invoice_number) {
                this.return_invoice_number = false;
            }
            if (this.void_invoice_number) {
                this.void_invoice_number = false;
            }
            this.original_inv_ref = false;
            this.invoice_number = this.pos.nextInvoiceNumber();
        }

        return removeLLine;
    },

    updatePricelistAndFiscalPosition(newPartner) {
        if(this.hmrc_is_refund_order || this.hmrc_is_return_order || this.hmrc_is_void_order){
            return;
        }
        super.updatePricelistAndFiscalPosition(...arguments);
    }
});


patch(ReceiptScreen.prototype, {
    setup() {
        super.setup();
        this.isReceiptSaved = false;

        onMounted(async () => {
            const order = this.currentOrder;

            if (order?.server_id && !order.receipt_text && !this.isReceiptSaved) {
                try {
                    await new Promise(resolve => setTimeout(resolve, 0));

                    const containers = document.querySelectorAll('.pos-receipt');
                    const container = containers[containers.length - 1];
                    if (!container) return;

                    let formattedText = '';
                    const LINE_WIDTH = 100;

                    const receiptEls = container.querySelectorAll('.pos-receipt-line');
                    const receiptEl1 = container.querySelectorAll('.pos-receipt-contact');
                    const receiptEl2 = container.querySelectorAll('.order-total');
                    const receiptEl3 = container.querySelectorAll('.paymentlines');
                    const receiptEls5 = container.querySelectorAll('.my-3');
                    const receiptEl6 = container.querySelectorAll('.footer_customer');
                    const receiptEl7 = container.querySelectorAll('.pos-receipt-center-align');

                    // HEADER
                    receiptEl1.forEach((el) => {
                        el.innerText.split('\n').forEach((line) => {
                            const cleanLine = line.trim();
                            if (!cleanLine || cleanLine.includes('MIXED SALE')) return;

                            formattedText += `${cleanLine}\n`;

                            if (cleanLine.includes('VAT REG TIN')) formattedText += `\n`;
                            if (cleanLine.startsWith('S/N')) formattedText += `\n\n`;
                        });
                    });

                    // ITEMS
                    formattedText += `\n\n`;
                    receiptEls.forEach((el) => {
                        const lines = el.innerText.split('\n');

                        for (let i = 0; i < lines.length; i++) {
                            const line = lines[i].trim();
                            const nextLine = lines[i + 1]?.trim();

                            if (line && line.includes('₱') && nextLine && nextLine.includes('₱')) {
                                const slashIndex = line.lastIndexOf('₱');
                                const itemPart = line.substring(0, slashIndex).trim();
                                const unitPrice = `"₱ ${line.substring(slashIndex + 1).trim()}"`;
                                const lineTotal = `"₱ ${nextLine.replace('₱', '').trim()}"`;

                                const left = `${itemPart} ${unitPrice}`;
                                const spaces = ' '.repeat(
                                    Math.max(1, LINE_WIDTH - (left.length + lineTotal.length))
                                );
                                formattedText += `${left}${spaces}${lineTotal}\n`;
                                i++;

                            } else if (line && line.includes('₱')) {
                                const parts = line.split('₱');
                                const left = parts[0].trim();
                                const right = `"₱ ${parts[1].trim()}"`;
                                const spaces = ' '.repeat(
                                    Math.max(1, LINE_WIDTH - (left.length + right.length))
                                );
                                formattedText += `${left}${spaces}${right}\n`;

                            } else if (line && !line.includes('₱') && nextLine && nextLine.includes('₱')) {
                                const left = `${line}`;
                                const right = `"₱ ${nextLine.replace('₱', '').trim()}"`;
                                const spaces = ' '.repeat(
                                    Math.max(1, LINE_WIDTH - (left.length + right.length))
                                );
                                formattedText += `${left}${spaces}${right}\n`;
                                i++;

                            } else if (line) {
                                formattedText += `${line}\n`;
                            }
                        }
                    });

                    // TOTALS + PAYMENTS
                    const processBlock = (elements) => {
                        elements.forEach((el) => {
                            const lines = el.innerText.split('\n');

                            for (let i = 0; i < lines.length; i++) {
                                const line = lines[i].trim();
                                const nextLine = lines[i + 1]?.trim();

                                if (line && nextLine && !line.includes('₱') && nextLine.includes('₱')) {
                                    const left = `${line} :`;
                                    const right = `"${nextLine.replace(/"/g, '').trim()}"`;
                                    const spaces = ' '.repeat(Math.max(1, LINE_WIDTH - (left.length + right.length)));

                                    formattedText += `${left}${spaces}${right}\n`;
                                    i++;
                                } else if (line) {
                                    formattedText += `${line}\n`;
                                }
                            }
                        });
                    };

                    formattedText += `\n\n`;
                    processBlock(receiptEl2);
                    processBlock(receiptEl3);

                    // EXTRA BLOCK
                    formattedText += `\n\n`;
                    receiptEls5.forEach((el) => {
                        const lines = el.innerText.split('\n');

                        for (let i = 0; i < lines.length; i++) {
                            const line = lines[i].trim();
                            const nextLine = lines[i + 1]?.trim();

                            if (line && nextLine && !line.includes('₱') && !line.includes('.') && nextLine.includes('₱')) {
                                const left = `${line} :`;
                                const right = `"${nextLine.replace(/"/g, '').trim()}"`;
                                const spaces = ' '.repeat(Math.max(1, LINE_WIDTH - (left.length + right.length)));

                                formattedText += `${left}${spaces}${right}\n`;
                                i++;
                            } else if (line && !line.includes('Print Receipt')) {
                                formattedText += `${line}\n`;
                            }
                        }
                    });

                    // CUSTOMER
                    formattedText += `\n\n`;
                    receiptEl6.forEach((el) => {
                        el.innerText.split('\n').forEach((line) => {
                            let cleanLine = line.trim();

                            if (!cleanLine) {
                                formattedText += `\n`;
                                return;
                            }

                            if (cleanLine.includes(':')) {
                                let [label, value] = cleanLine.split(':');
                                value = value?.trim() || '___________';
                                formattedText += `${label.trim()}: ${value}\n`;
                            } else {
                                formattedText += `${cleanLine}\n`;
                            }
                        });
                    });

                    // FOOTER
                    formattedText += `\n\n`;
                    let first = true;

                    receiptEl7.forEach((el) => {
                        el.innerText.split('\n').forEach((line) => {
                            const cleanLine = line.trim();
                            if (!cleanLine) return;

                            formattedText += `${cleanLine}\n`;

                            if (first && cleanLine.includes('THIS SERVES AS A SALES INVOICE')) {
                                formattedText += `\n`;
                                first = false;
                            }
                        });
                    });

                    // SAVE
                    if (order?.server_id && !order.receipt_text) {
                        await this.orm.call(
                            "pos.order",
                            "write",
                            [[order.server_id], { receipt_text: formattedText }]
                        );
                    }

                    this.isReceiptSaved = true;

                } catch (e) {
                    console.error("Error:", e);
                }
            }
        });
    },


    async printReceipt() {
        if (!this.isReceiptSaved) return;

        const order = this.currentOrder;

        if (!order.print_count) {
            order.print_count = 0;
        }

        if (order.print_count > 0) {
            const { confirmed, payload } = await this.popup.add(TextAreaPopup, {
                title: _t("Reason for Reprinting"),
                confirmText: _t("Print"),
                cancelText: _t("Cancel"),
            });

            if (!confirmed) return;

            const reason = payload?.trim() || "No reason provided";

            if (order.server_id) {
                const htmlMessage = `
                    <div>
                        <strong>Receipt Reprinted By ${this.pos.get_cashier()?.name || "Unknown"}</strong><br/>
                        <span>${formatDateTime(luxon.DateTime.now())}</span><br/>
                        <span>${this.pos.pos_session?.name || "Unknown"}</span><br/>
                        <span>Reason: ${reason}</span>
                    </div>
                `;

                await this.orm.call("pos.order", "message_post", [[order.server_id]], {
                    body: htmlMessage,
                });
            }
        }

        await super.printReceipt();
        order.print_count += 1;
    },

    async backToProducts() {
        if (!this.isReceiptSaved) return;
        return super.backToProducts();
    }

});

patch(Orderline.prototype, {
    setup(_defaultObj, options) {
        super.setup(...arguments);
        this.is_sc_line = this.is_sc_line || false;
        this.vat_removeds = this.vat_removeds || [];
        this.vat_removed_amount = this.vat_removed_amount || 0;
        this.vat_reapplied = this.vat_reapplied || 0;
        this.discount_amount = this.discount_amount || 0;
        this.is_sc_bnpc_discount = this.is_sc_bnpc_discount || false;
        this.is_sc_bnpc_discount_amount = this.is_sc_bnpc_discount_amount || 0;
        this.net_vatable_sales = this.net_vatable_sales || 0;
        this.is_sc_line_discount = this.is_sc_line_discount || false;
        this.is_pwd_line_discount = this.is_pwd_line_discount || false;
        this.discount_vat_treatment = this.discount_vat_treatment || false;
        this.appliedDiscountConfig = this.appliedDiscountConfig || false;
        this.applied_discount_name = this.applied_discount_name || false;
        this.applied_on_line_text = this.applied_on_line_text || false;
    },

    set_quantity(quantity, keep_price) {
        let res = super.set_quantity(...arguments);
        let order = this.pos.get_order();
        if(this.is_sc_line){
            this.apply_bir_discount();
        }
        if(this.is_sc_bnpc_discount) {
            this.apply_basic_necessity_discount();
        }
        return res;
    },

    getDisplayData() {
        let result = super.getDisplayData();
        let discount = this.env.utils.formatProductQty(parseFloat(result['discount']) || 0);
        let customer = this.order?.get_partner();
        result['discount'] = discount;
        return {
            ...super.getDisplayData(),
            is_sc_line: this.is_sc_line,
            vat_removeds: this.vat_removeds || [],
            vat_removed_amount: this.env.utils.formatCurrency(-this.vat_removed_amount),
            discount_amount: this.env.utils.formatCurrency(-this.discount_amount),
            original_price: this.env.utils.formatCurrency(this.quantity * this.getBasePrice().originalPrice),
            is_sc_bnpc_discount: this.is_sc_bnpc_discount,
            is_sc_bnpc_discount_amount: this.env.utils.formatCurrency(-this.is_sc_bnpc_discount_amount),
            net_vatable_sales: this.env.utils.formatCurrency(this.net_vatable_sales),
            is_sc_line_discount: this.is_sc_line_discount,
            is_pwd_line_discount: this.is_pwd_line_discount,
            discount_vat_treatment: this._getVatTreatment(),
            senior_pwd_person: customer?.senior_pwd_person,
            naac_id_no: customer?.naac_id_no,
            sc_id_no: customer?.sc_id_no,
            pwd_id_no: customer?.pwd_id_no,
            spic_id_no: customer?.spic_id_no,
            applied_discount_name: this.applied_discount_name || (this.appliedDiscountConfig ? (this.appliedDiscountConfig.on_line_text || this.appliedDiscountConfig.name) : false),
            applied_on_line_text: this.applied_on_line_text || (this.appliedDiscountConfig ? (this.appliedDiscountConfig.on_line_text || this.appliedDiscountConfig.name) : false),
            appliedDiscountText: this.applied_on_line_text || this.applied_discount_name || (this.appliedDiscountConfig ? (this.appliedDiscountConfig.on_line_text || this.appliedDiscountConfig.name) : false),
            sh_model_line: this,

        };
    },

    export_as_JSON() {
        const result = super.export_as_JSON(...arguments);

        result.is_sc_line = this.is_sc_line;
        result.vat_removeds = this.vat_removeds;
        result.vat_removed_amount = this.vat_removed_amount;
        result.vat_reapplied = this.vat_reapplied;
        result.discount_amount = this.discount_amount;
        result.is_sc_bnpc_discount = this.is_sc_bnpc_discount;
        result.is_sc_bnpc_discount_amount = this.is_sc_bnpc_discount_amount;
        result.net_vatable_sales = this.net_vatable_sales;
        result.is_sc_line_discount = this.is_sc_line_discount;
        result.is_pwd_line_discount = this.is_pwd_line_discount;
        result.applied_discount_id = Number(
            this.applied_discount_id ||
            (this.appliedDiscountConfig ? this.appliedDiscountConfig.id : 0)
        ) || false;
        result.applied_discount_name = this.applied_discount_name || 
            (this.appliedDiscountConfig ? (this.appliedDiscountConfig.on_line_text || this.appliedDiscountConfig.name) : false);
        result.applied_on_line_text = this.applied_on_line_text || 
            (this.appliedDiscountConfig ? (this.appliedDiscountConfig.on_line_text || this.appliedDiscountConfig.name) : false);
        result.discount_vat_treatment = this._getVatTreatment();
            
        result.applied_discount_code = this.appliedDiscountConfig?.discount_code || this.applied_discount_code || false;
        return result;
    },

    init_from_JSON(json) {
        super.init_from_JSON(...arguments);
        this.is_sc_line = json.is_sc_line;
        this.vat_removeds = json.vat_removeds || [];
        this.vat_removed_amount = json.vat_removed_amount || 0;
        this.vat_reapplied = json.vat_reapplied || 0;
        this.discount_amount = json.discount_amount || 0;
        this.is_sc_bnpc_discount = json.is_sc_bnpc_discount;
        this.is_sc_bnpc_discount_amount = json.is_sc_bnpc_discount_amount || 0;
        this.net_vatable_sales = json.net_vatable_sales || 0;
        this.is_sc_line_discount = json.is_sc_line_discount || false;
        this.is_pwd_line_discount = json.is_pwd_line_discount || false;
        this.applied_discount_id = json.applied_discount_id || false;
        this.applied_discount_name = json.applied_discount_name || false;
        this.applied_on_line_text = json.applied_on_line_text || false;
        this.applied_discount_code = json.applied_discount_code || false;
        // Store in persistent cache for refund detail lookup
        if (this.id && this.applied_discount_code) {
            _discountCodeCache.set(this.id, this.applied_discount_code);
        }
        this.discount_vat_treatment = json.discount_vat_treatment || false;
        this.vat_reapplied = json.vat_reapplied || 0;
        this.vat_amount_output = json.vat_amount_output || 0;
        this.total_amount_due = json.total_amount_due || 0;

        if (json.applied_discount_code) {
            this.appliedDiscountConfig = this.pos.getDiscountConfig(json.applied_discount_code);
        }

        if (!this.appliedDiscountConfig && this.applied_discount_id) {
            const allConfigs = this.pos.discountConfigs || [];
            this.appliedDiscountConfig = allConfigs.find(c => c.id === this.applied_discount_id) || null;
        }

        if (this.appliedDiscountConfig && !this.applied_discount_id) {
            this.applied_discount_id = this.appliedDiscountConfig.id;
        }
    },

    getBasePrice() {
        const taxIncludedPrice = this.product.get_display_price();
        const totalRate = this._getProductTaxesAfterFiscalPosition()
            .reduce((sum, t) => sum + t.amount, 0);
        const basePrice = taxIncludedPrice / (1 + totalRate / 100);

        return {
            basePrice: + basePrice.toFixed(3),
            taxAmount: + (taxIncludedPrice - basePrice).toFixed(3),
            totalRate,
            originalPrice: + basePrice.toFixed(3) + + (taxIncludedPrice - basePrice).toFixed(3),
        };
    },

    apply_basic_necessity_discount(){
        if(this.is_sc_bnpc_discount) return;
        this.is_sc_bnpc_discount_amount = (this.getBasePrice().originalPrice * 0.05) * this.quantity;
        let wo_vat_amount = this.getBasePrice().basePrice * this.quantity;
        let vat_amount = this.getBasePrice().taxAmount * this.quantity;
        const totalRate = this._getProductTaxesAfterFiscalPosition()
        .reduce((sum, t) => sum + t.amount, 0);
        const vatFactor = 1 + (totalRate / 100);
        this.net_vatable_sales = wo_vat_amount - (this.is_sc_bnpc_discount_amount / vatFactor);
        this.vat_amount_output = vatFactor * this.net_vatable_sales;
        this.total_amount_due = this.net_vatable_sales + this.vat_amount_output;
        this.is_sc_bnpc_discount = true;
        this.is_sc_line = true;
        this.set_discount(5);
    },


    apply_bir_discount(){
         const discountCode = this.applied_discount_code || this.order?.get_partner()?.senior_pwd_person;
         if ( discountCode === 'medal'){
            let txs = this._getProductTaxesAfterFiscalPosition()
            this.vat_removeds = txs.map((t)=>t.name);
            this.vat_removed_amount = this.quantity * (this.getBasePrice().taxAmount);
            this.discount_amount = (this.getBasePrice().basePrice * 0.2) * this.quantity;
            this.is_sc_line = true;
         }
         else if(discountCode === 'spic') {
                let txs = this._getProductTaxesAfterFiscalPosition()
                this.vat_removeds = txs.map((t)=>t.name);
                this.vat_removed_amount = this.quantity * (this.getBasePrice().taxAmount);
                this.discount_amount = (this.getBasePrice().basePrice * 0.1) * this.quantity;
                this.is_sc_line = true;
         }
         else{
            let txs = this._getProductTaxesAfterFiscalPosition()
            this.vat_removeds = txs.map((t)=>t.name);
            this.vat_removed_amount = this.quantity * (this.getBasePrice().taxAmount);
            this.discount_amount = (this.getBasePrice().basePrice * (this.discount / 100)) * this.quantity;
            this.is_sc_line = true;
         }

    },

    get_all_prices(qty = this.get_quantity()) {
        let result = super.get_all_prices(...arguments);
        const bp = this.getBasePrice();
        const customer = this.order?.get_partner();
        const vatTreatment = this._getVatTreatment();
        const reapplying = (-this.quantity) * bp.taxAmount;
        const isRefund = this.order?.hmrc_is_refund_order || this.order?.hmrc_is_void_order || this.order?.hmrc_is_return_order;

        if (customer?.senior_pwd_person === 'naac' || this.is_sc_bnpc_discount) {
            this.vat_reapplied = this.quantity * bp.taxAmount;
        }


        if (this.is_sc_line) {
            if (this.vat_reapplied && this.vat_reapplied > 0 || this.vat_reapplied && this.vat_reapplied<0)  {
                const customer = this.order?.get_partner();
                const RefundOrder = this.order;
                if (RefundOrder.hmrc_is_refund_order || RefundOrder.hmrc_is_void_order || RefundOrder.hmrc_is_return_order && customer?.senior_pwd_person === 'naac') {

                    result['priceWithTax'] = result['priceWithoutTax'] + (reapplying / (-this.quantity)) ;
                    result['tax'] = this.vat_reapplied;
                    result['priceWithTaxBeforeDiscount'] = result['priceWithTaxBeforeDiscount'];
                }
                else{
                    result['priceWithTax'] = result['priceWithoutTax'] + (this.vat_reapplied)/this.quantity;
                    result['tax'] = this.vat_reapplied;
                    result['priceWithTaxBeforeDiscount'] = result['priceWithTaxBeforeDiscount'];
                }

            }
            else if (vatTreatment === 'vat_inclusive'){
                result['priceWithTax'] = result['priceWithoutTax'];
                result['tax'] = this.vat_reapplied || 0;
                result['priceWithTaxBeforeDiscount'] = result.totalAmountDue * qty;
            }
            else {
                result['priceWithTax'] = result['priceWithoutTax'];
                result['tax'] = 0;
                result['priceWithTaxBeforeDiscount'] = result['priceWithoutTaxBeforeDiscount'];
           }

        }

        if (this.is_sc_bnpc_discount) {
            result['priceWithTax'] = result['priceWithoutTax'] + (reapplying / (-this.quantity)) ;
            result['tax'] = this.vat_reapplied;
            result['priceWithTaxBeforeDiscount'] = this.getBasePrice().originalPrice * qty;
        }

        return result;
    }
})
