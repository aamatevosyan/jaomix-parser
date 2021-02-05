arr = document.querySelectorAll(".title a");
urls = [];
titles = [];

for (let i = 0; i < arr.length; i++) {
    urls.push(arr.item(i).href)
}

for (let i = 0; i < arr.length; i++) {
    titles.push(arr.item(i).textContent)
}

urls.reverse();
titles.reverse();

return JSON.stringify({
    name: document.querySelector(".desc-book h1").textContent,
    author: document.querySelector("#info-book p").textContent.substr(7),
    description: document.querySelector("#desc-tab p").textContent,
    cover_path: document.querySelector(".img-book img").src,
    urls: urls,
    titles: titles
});