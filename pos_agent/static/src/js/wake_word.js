/** @odoo-module **/
import { patch } from "@web/core/utils/patch";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { usePos } from "@point_of_sale/app/store/pos_hook";

let pos = null;
let initialized = false;
let paymentScreenInstance = null;

patch(ProductScreen.prototype, {
    setup() {
        super.setup(...arguments);
        pos = usePos();
        if (!initialized) {
            initialized = true;
            setupVoiceRecognition();
        }
    },
});

patch(PaymentScreen.prototype, {
    setup() {
        super.setup(...arguments);
        paymentScreenInstance = this;
    },
});

let speaking = false;

function speak(text) {
    console.log(`VOICE: "${text}"`);
    if (!window.speechSynthesis) return;
    speaking = true;
    window.speechSynthesis.cancel();
    // Safety: auto-reset speaking flag after 2s (in case onend never fires)
    const safetyTimer = setTimeout(() => { speaking = false; }, 2000);
    const utter = new SpeechSynthesisUtterance(text);
    utter.lang = "en-US";
    utter.rate = 1;
    const done = () => { clearTimeout(safetyTimer); speaking = false; };
    utter.onend = done;
    utter.onerror = done;
    try { window.speechSynthesis.speak(utter); } catch (e) { console.warn("TTS error:", e); clearTimeout(safetyTimer); speaking = false; }
}

function getPosProducts() {
    if (!pos || !pos.db) return [];
    return Object.values(pos.db.product_by_id || {});
}

function scoreMatch(query, name) {
    const q = query.toLowerCase().trim();
    const n = name.toLowerCase().trim();
    if (!q || !n) return 0;
    if (n === q) return 100;
    if (n.includes(q)) return 90;
    if (q.includes(n)) return 85;
    const qWords = q.split(/\s+/).filter(Boolean);
    const nWords = n.split(/\s+/).filter(Boolean);
    const common = qWords.filter(w => nWords.some(nw => nw.includes(w) || w.includes(nw)));
    const tokenScore = qWords.length ? (common.length / qWords.length) * 70 : 0;
    let charMatch = 0;
    for (let i = 0; i < Math.min(q.length, n.length); i++) {
        if (q[i] === n[i]) charMatch++;
    }
    const charScore = (charMatch / Math.max(q.length, n.length)) * 30;
    return Math.round(tokenScore + charScore);
}

function findBestProduct(text) {
    const products = getPosProducts();
    let best = null, bestScore = 0;
    for (const p of products) {
        const name = p.display_name || p.name || "";
        const score = scoreMatch(text, name);
        if (score > bestScore) { bestScore = score; best = p; }
    }
    if (best && bestScore >= 30) return { product: best, score: bestScore };
    return null;
}

const NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4,
    "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
};
const NUMBER_WORD_PATTERN = new RegExp(
    "\\b(" + Object.keys(NUMBER_WORDS).join("|") + ")\\b", "gi"
);

function parseQuantity(text) {
    const digitMatch = text.match(/\d+/);
    if (digitMatch) return Math.max(1, parseInt(digitMatch[0]));
    const wordMatch = text.match(NUMBER_WORD_PATTERN);
    if (wordMatch) return NUMBER_WORDS[wordMatch[0].toLowerCase()];
    return 0;
}
function removeQuantity(text) {
    let t = text;
    const digitMatch = t.match(/\d+/);
    if (digitMatch) t = t.replace(digitMatch[0], "");
    t = t.replace(NUMBER_WORD_PATTERN, "");
    return t.trim().replace(/\s+/g, " ");
}
function stripFillers(text) {
    let t = text;
    const fillers = ["add","i want","i need","give me","want","need","please","can i have","i would like","id like"];
    for (const f of fillers) t = t.replace(new RegExp(f, "gi"), "").trim();
    return t.replace(/\s+/g, " ");
}

const WAKE_WORDS = ["hey siri", "hello odoo", "hey odoo"];
const REMOVE_WORDS = ["remove","delete","cancel","hatao","hatado","nikal","hata"];
function isWakeCommand(text) {
    return WAKE_WORDS.some(w => text.includes(w));
}
function stripWakeWord(text) {
    let t = text;
    for (const w of WAKE_WORDS) t = t.replace(new RegExp(w, "gi"), "").trim();
    return t.replace(/\s+/g, " ");
}
function isClearCommand(text) {
    const p = ["clear cart","clear all","clear order","clear","remove all","remove everything","empty cart","delete all","start over","cancel order"];
    return p.some(v => text.includes(v));
}
function isSleepCommand(text) {
    const w = ["stop","bye","sleep","close","goodbye","thats all","that's all","enough","bas","go to sleep","shut up","stop listening"];
    return w.some(x => new RegExp(`\\b${x}\\b`, "i").test(text));
}
function isRemoveCommand(text) {
    return REMOVE_WORDS.some(w => new RegExp(`\\b${w}\\b`, "i").test(text));
}
function getRemoveProductName(text) {
    let name = text;
    for (const w of REMOVE_WORDS) name = name.replace(new RegExp(w, "gi"), "").trim();
    name = name.replace(/\d+/g, "").replace(NUMBER_WORD_PATTERN, "").trim();
    return stripFillers(name).replace(/\s+/g, " ");
}

function clearCart() {
    const order = pos.get_order();
    if (!order || !order.orderlines.length) { speak("Cart is already empty"); return; }
    const lines = []; order.orderlines.forEach(l => lines.push(l));
    lines.forEach(l => order.orderlines.remove(l));
    speak("All items removed from cart");
}
function removeProductFromCart(productName, qty) {
    const order = pos.get_order();
    if (!order || !order.orderlines.length) { speak("Cart is empty, nothing to remove"); return; }
    const lines = []; order.orderlines.forEach(l => lines.push(l));
    const query = productName.toLowerCase();
    for (const line of lines) {
        const lineName = (line.get_full_product_name?.() || line.product?.name || "").toLowerCase();
        if (lineName.includes(query)) {
            const name = line.product?.name || lineName;
            const currentQty = line.get_quantity();
            if (qty > 0 && qty < currentQty) {
                line.set_quantity(currentQty - qty);
                speak(`${qty} ${name} removed, ${Math.round(currentQty - qty)} remaining`);
            } else {
                order.orderlines.remove(line);
                speak(`${name} has been removed from your cart`);
            }
            return;
        }
    }
    speak(`I could not find ${productName} in your cart`);
}
async function addProduct(productName, qty) {
    const result = findBestProduct(productName);
    if (!result) { speak(`Sorry, ${productName} is not available in this POS`); return; }
    const p = result.product;
    console.log(`Found: ${p.name} (score: ${result.score})`);
    await pos.addProductToCurrentOrder(p.id, { quantity: qty || 1 });
    const label = qty > 1 ? `${qty} ${p.name}` : p.name;
    speak(`${label} added to cart`);
}

const CUSTOMER_WORDS = ["customer", "for customer", "select customer", "set customer"];
const ACTION_WORDS = ["add", "want", "need", "give", "remove", "delete", "cancel", "pay", "clear"];
const PAY_WORDS = ["pay", "checkout", "complete order", "payment", "bill"];

function isPayCommand(text) {
    return PAY_WORDS.some(w => new RegExp(`\\b${w}\\b`, "i").test(text));
}

function isCustomerCommand(text) {
    const t = text.toLowerCase().trim();
    const prev = t.match(/(\w+)\s+customer\b/);
    if (prev && ACTION_WORDS.includes(prev[1])) return false;
    return CUSTOMER_WORDS.some(w => new RegExp(`\\b${w}\\b`, "i").test(t));
}

function getCustomerName(text) {
    let name = text;
    const sorted = [...CUSTOMER_WORDS].sort((a, b) => b.length - a.length);
    for (const w of sorted) name = name.replace(new RegExp(w, "gi"), "").trim();
    return name.replace(/\s+/g, " ");
}

function searchCustomer(name) {
    const partners = Object.values(pos.db.partner_by_id || {});
    if (!partners.length) { speak("No customers available"); return; }
    const query = name.toLowerCase().trim();
    let best = null, bestScore = 0;
    for (const p of partners) {
        const pName = (p.name || "").toLowerCase();
        if (!pName) continue;
        let score = scoreMatch(query, pName);
        if (p.mobile && p.mobile.toLowerCase().includes(query)) score = Math.max(score, 80);
        if (score > bestScore) { bestScore = score; best = p; }
    }
    if (best && bestScore >= 40) {
        const order = pos.get_order();
        if (order) {
            order.set_partner(best);
            if (pos.tempScreen) {
                pos.tempScreen.props.resolve({ confirmed: false, payload: null });
                pos.closeTempScreen();
            }
            speak(`Customer set to ${best.name}`);
        }
    } else {
        speak(`Customer ${name} not found`);
    }
}

function goToPayment() {
    const order = pos.get_order();
    if (!order || !order.orderlines.length) {
        speak("Cart is empty, nothing to checkout");
        return;
    }
    pos.showScreen("PaymentScreen");
    speak("Payment screen opened");
}

function findPaymentMethod(text) {
    const t = text.toLowerCase();
    const methods = pos.payment_methods.filter(m =>
        pos.config.payment_method_ids.includes(m.id)
    );
    let best = null, bestScore = 0;
    for (const m of methods) {
        const s = scoreMatch(t, m.name);
        if (s > bestScore) { bestScore = s; best = m; }
    }
    return best && bestScore >= 40 ? best : null;
}

const VALIDATE_WORDS = ["validate", "confirm", "done", "finish", "complete"];

function isValidateCommand(text) {
    return VALIDATE_WORDS.some(w => new RegExp(`\\b${w}\\b`, "i").test(text));
}

function isOnPaymentScreen() {
    return pos.mainScreen?.name === "PaymentScreen" || !!paymentScreenInstance;
}

async function handleCommand(command) {
    try {
    if (isSleepCommand(command)) { speak("Okay, going to sleep. Say hey siri to wake me up."); return "sleep"; }
    if (isClearCommand(command)) { clearCart(); return "ok"; }
    if (isRemoveCommand(command)) {
        const rawQty = parseQuantity(command);
        const name = getRemoveProductName(command);
        if (name) removeProductFromCart(name, rawQty);
        else speak("Which product should I remove?");
        return "ok";
    }
    if (isOnPaymentScreen()) {
        if (isValidateCommand(command)) {
            if (paymentScreenInstance) {
                await paymentScreenInstance.validateOrder(true);
            }
            return "ok";
        }
        const method = findPaymentMethod(command);
        if (method) {
            const order = pos.get_order();
            if (order) {
                order.add_paymentline(method);
                speak(`${method.name} selected`);
            }
            return "ok";
        }
    }
    if (isPayCommand(command)) {
        goToPayment();
        return "ok";
    }
    if (isCustomerCommand(command)) {
        const name = getCustomerName(command);
        if (name) {
            await searchCustomer(name);
        } else {
            pos.selectPartner();
            speak("Customer selection opened");
        }
        return "ok";
    }
    const rawQty = parseQuantity(command);
    const productName = stripFillers(rawQty > 0 ? removeQuantity(command) : command);
    if (!productName) { speak("Please say a product name"); return "ok"; }
    await addProduct(productName, rawQty || 1);
    return "ok";
    } catch (e) { console.error("Command error:", e); return "ok"; }
}

function setupVoiceRecognition() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) { console.warn("Speech recognition not supported"); return; }

    const recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = false;
    recognition.lang = "en-US";

    let waitingForCommand = false;
    let processing = false;
    let waitingForCommandTimeout = null;

    function resetWaitingForCommandTimeout() {
        if (waitingForCommandTimeout) clearTimeout(waitingForCommandTimeout);
        waitingForCommandTimeout = setTimeout(() => { waitingForCommand = false; }, 30000);
    }

    let processTimeout = null;

    recognition.onresult = async (event) => {
        if (processing || speaking) return;
        processing = true;
        if (processTimeout) clearTimeout(processTimeout);
        processTimeout = setTimeout(() => { processing = false; }, 10000);
        try {
            const result = event.results[event.results.length - 1];
            if (!result.isFinal) return;
            const transcript = result[0].transcript.trim().toLowerCase();
            console.log("STT:", transcript);

            if (!waitingForCommand) {
                if (isWakeCommand(transcript)) {
                    waitingForCommand = true;
                    resetWaitingForCommandTimeout();
                    const rest = stripWakeWord(transcript);
                    if (rest) {
                        speak("Yes, I am listening");
                        const status = await handleCommand(rest);
                        if (status === "sleep") waitingForCommand = false;
                    } else {
                        speak("Yes, I am listening");
                    }
                }
                return;
            }
            resetWaitingForCommandTimeout();
            const status = await handleCommand(transcript);
            if (status === "sleep") waitingForCommand = false;
        } catch (e) {
            console.error("Voice handler error:", e);
        } finally {
            if (processTimeout) clearTimeout(processTimeout);
            processing = false;
        }
    };

    let restartTimer = null;

    function safeRestart() {
        if (restartTimer) clearTimeout(restartTimer);
        restartTimer = setTimeout(() => {
            try { recognition.start(); } catch (e) { console.log("Restart failed:", e); }
        }, 100);
    }

    recognition.onstart = () => console.log("Mic listening...");
    recognition.onerror = (e) => {
        console.log("Mic error:", e.error);
        if (e.error === "not-allowed") {
            console.warn("Microphone permission denied — cannot restart");
            return;
        }
        safeRestart();
    };
    recognition.onend = () => {
        console.log("Mic stopped — restarting...");
        safeRestart();
    };
    recognition.start();
}
