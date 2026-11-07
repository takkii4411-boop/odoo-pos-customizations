/** @odoo-module */

import { PosStore } from "@point_of_sale/app/store/pos_store";
import { patch } from "@web/core/utils/patch";

patch(PosStore.prototype, {

    async openCashControl() {
        if (this._sh_login_done) {
            super.openCashControl();
            return;
        }

        if (this.config.module_pos_hr) {
            this._sh_login_done = true;
            this.hasLoggedIn = false;

            sessionStorage.removeItem(`connected_cashier_${this.config.id}`);

            this.reset_cashier();

            await this.showTempScreen("LoginScreen");
            return;
        }

        this._sh_login_done = true;
        super.openCashControl();
    },

});