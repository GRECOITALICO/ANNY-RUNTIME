const txt = "hello\n";
const tagName = "INPUT";
if (tagName.toLowerCase() !== 'textarea' && (txt.includes('\n') || txt.includes('\r'))) {
    console.log("blocked");
} else {
    console.log("ok");
}
