const cart = [];
const cartEl = document.getElementById("cart");
const confirmation = document.getElementById("confirmation");
const results = document.getElementById("results");

function updateCart() {
  const count = cart.length;
  cartEl.textContent = "Cart: " + count + (count === 1 ? " item" : " items");
}

document.getElementById("add-to-cart").addEventListener("click", () => {
  cart.push("Blue mug");
  updateCart();
});

document.getElementById("checkout").addEventListener("click", () => {
  if (cart.length === 0) {
    cartEl.textContent = "Cart is empty";
    return;
  }
  confirmation.hidden = false;
});

document.getElementById("search-form").addEventListener("submit", (event) => {
  event.preventDefault();
  results.hidden = false;
});
