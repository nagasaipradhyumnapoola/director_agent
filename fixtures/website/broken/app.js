const cartEl = document.getElementById("cart");
const confirmation = document.getElementById("confirmation");

document.getElementById("add-to-cart").addEventListener("click", () => {
  undefinedCheckoutHelper();
  cartEl.textContent = "Cart: 1 item";
});

// Checkout is intentionally unwired: the primary journey cannot complete.
void confirmation;
