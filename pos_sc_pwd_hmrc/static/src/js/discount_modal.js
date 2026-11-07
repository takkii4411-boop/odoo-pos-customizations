/** @odoo-module **/

import { AbstractAwaitablePopup } from "@point_of_sale/app/popup/abstract_awaitable_popup";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { ErrorPopup } from "@point_of_sale/app/errors/popups/error_popup";
import { SelectionPopup } from "@point_of_sale/app/utils/input_popups/selection_popup";
import { NumberPopup } from "@point_of_sale/app/utils/input_popups/number_popup";
import { usePos } from "@point_of_sale/app/store/pos_hook";

/**
 * First Modal - Discount Type Selection
 * Opens when user clicks "% Disc" button
 */
export class DiscountTypeSelectionPopup extends AbstractAwaitablePopup {
    static template = "pos_sc_pwd_hmrc.DiscountTypeSelectionPopup";
    static defaultProps = {
        confirmText: _t("Select"),
        cancelText: _t("Cancel"),
        title: _t("Select Discount Type"),
    };

    setup() {
        super.setup();
        this.pos = usePos();
    }

    /**
     * Handle Regular Discount selection
     */
    async selectRegularDiscount() {
        this.confirm();
        this.props.resolve({ confirmed: true, payload: 'regular' });
    }

    /**
     * Handle Special Discount selection
     * This will trigger manager approval flow
     */
    async selectSpecialDiscount() {
        this.confirm();
        this.props.resolve({ confirmed: true, payload: 'special' });
    }
}

/**
 * Manager Approval Modal
 * Opens when user selects "Special Discounts"
 */
export class ManagerApprovalPopup extends AbstractAwaitablePopup {
    static template = "pos_sc_pwd_hmrc.ManagerApprovalPopup";
    static defaultProps = {
        confirmText: _t("Approve"),
        cancelText: _t("Cancel"),
        title: _t("Manager Approval Required"),
        body: _t("Special discounts require manager authorization. Please select a manager to continue."),
    };

    setup() {
        super.setup();
        this.pos = usePos();
        this.popup = useService("popup");
    }

    /**
     * Request manager approval
     */
    async requestApproval() {
        const order = this.pos.get_order();
        const partner = order?.get_partner();

        // Validation: Check if customer is selected
        if (!partner) {
            await this.popup.add(ErrorPopup, {
                title: _t("No Eligible Customer"),
                body: _t("Please select a customer with special discount eligibility first."),
            });
            this.cancel();
            return;
        }

        // Check if HR module is enabled
        if (!this.pos.config.module_pos_hr) {
            // No HR module - approve automatically
            this.approveSpecialDiscountMode(partner);
            return;
        }

        // Get list of managers
        const employeesList = this.pos.employees
            .filter((employee) => employee.role === "manager")
            .map((employee) => ({
                id: employee.id,
                item: employee,
                label: employee.name,
                isSelected: false,
            }));

        if (!employeesList.length) {
            await this.popup.add(ErrorPopup, {
                title: _t("No Managers"),
                body: _t("There are no managers available. Please configure managers in HR settings."),
            });
            this.cancel();
            return;
        }

        // Select manager
        const { confirmed, payload: employee } = await this.popup.add(SelectionPopup, {
            title: _t("Select Manager"),
            list: employeesList,
        });

        if (!confirmed || !employee) {
            this.cancel();
            return;
        }

        // Check PIN if employee has one
        if (employee.pin) {
            const { confirmed: pinConfirmed, payload: inputPin } = await this.popup.add(NumberPopup, {
                isPassword: true,
                title: _t("Enter Manager Password"),
            });

            if (!pinConfirmed) {
                this.cancel();
                return;
            }

            if (employee.pin !== Sha1.hash(inputPin)) {
                await this.popup.add(ErrorPopup, {
                    title: _t("Incorrect Password"),
                    body: _t("Please try again."),
                });
                this.cancel();
                return;
            }
        }

        // Approval successful
        this.approveSpecialDiscountMode(partner);
    }

    /**
     * Enable special discount mode for current order
     */
    approveSpecialDiscountMode(partner) {
        const order = this.pos.get_order();

        // Enable special discount mode
        order.specialDiscountModeEnabled = true;
        order.activeDiscountType = null; // Will be set when button is toggled

        console.log(`[Manager Approval] Special discount mode enabled for order ${order.uid}`);

        this.confirm();
        this.props.resolve({
            confirmed: true,
            payload: {
                approved: true,
                customerType: partner.senior_pwd_person
            }
        });
    }
}