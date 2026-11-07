/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { WebClient } from "@web/webclient/webclient";
import { onMounted } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

patch(WebClient.prototype, {
    setup() {
        super.setup();

        this.orm = useService("orm");

        onMounted(async () => {

            if (document.querySelector("#bottom_left_logo")) return;

            let result = await this.orm.searchRead(
                "sh.pos.theme.settings",
                [],
                ["theme_logo", "primary_color"]
            );

            let logoUrl = "";
            let bgColor = null;

            if (result.length) {
                const data = result[0];

                if (data.theme_logo) {
                    logoUrl = `/web/image/sh.pos.theme.settings/${data.id}/theme_logo`;
                }

                if (data.primary_color) {
                    bgColor = data.primary_color;
                }
            }

            const div = document.createElement("div");
            div.id = "bottom_left_logo";

            div.style.position = "fixed";
            div.style.bottom = "0";
            div.style.left = "0";
            div.style.width = "100%";
            div.style.height = "50px";
            div.style.display = "flex";
            div.style.alignItems = "center";
            div.style.padding = "0 15px";
            div.style.zIndex = "9999";

            if (bgColor) {
                div.style.background = bgColor;
            }

            div.innerHTML = `
                <img src="${logoUrl}" style="height:40px;" />

            `;
            document.body.appendChild(div);
            const resizeObserver = new ResizeObserver(() => {
                document.body.style.paddingBottom = div.offsetHeight + 'px';
            });
            resizeObserver.observe(div);

            document.body.style.paddingBottom = div.offsetHeight + 'px';
         });
    },
});