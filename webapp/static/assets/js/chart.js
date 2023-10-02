
/*ctx = document.getElementById("c").getContext("2d");

ctx.beginPath();

canvas_arrow(ctx, 500, 100, 500, 50);
ctx.stroke();


function canvas_arrow(context, fromx, fromy, tox, toy) {
  var headlen = 10; // length of head in pixels
  var dx = tox - fromx;
  var dy = toy - fromy;
  var angle = Math.atan2(dy, dx);
 
  context.moveTo(fromx, fromy);
  context.lineTo(tox, toy);
  context.lineTo(tox - headlen * Math.cos(angle - Math.PI / 6), toy - headlen * Math.sin(angle - Math.PI / 6));
  context.moveTo(tox, toy);
  context.lineTo(tox - headlen * Math.cos(angle + Math.PI / 6), toy - headlen * Math.sin(angle + Math.PI / 6));
}

*/

// https://codepen.io/jacobvarner/pen/eYOPVdK 

(function(d) {
  
  //document.getElementById('myCanvas').width= window.innerWidth;
  //document.getElementById('myCanvas').height = window.innerHeight;
  //document.getElementById('myCanvas').style.height = '500px';
  

  let Start = document.getElementById("Start");
  let button2 = document.getElementById("button2");
  let button3 = document.getElementById("button3");
  let End = document.getElementById("End");

  connectItems(Start, button2, "right", "top");
  connectItems(Start, button3, "bottom", "left");
  connectItems(Start, End, "right", "top");
  connectItems(button2, End, "bottom", "left");
  connectItems(button3, End, "bottom", "left");
})(document);




function connectItems(item1, item2, startPosition, endPosition) {
  let canvas = document.getElementById("flowchart");
  let ctx = canvas.getContext("2d");
  const width = 2;
  const color = 'gray';
  const head_len = 16;
  const head_angle = Math.PI / 6;
  let angle = 0;

  ctx.fillStyle = color;
  ctx.strokeStyle = color;
  ctx.lineJoin = 'red';
  ctx.lineWidth = width;

  item1 = item1.getBoundingClientRect();
  item2 = item2.getBoundingClientRect();
  console.log("connecting ", item1, " to ", item2);
  
  let startX, startY, endX, endY = 0.0;
  
  switch (startPosition) {
    case "top":
      startX = item1.width / 2 + item1.left;
      startY = item1.top;
      break;
    case "right":
      startX = item1.width + item1.left;
      startY = item1.height / 2 + item1.top;
      break;
    case "bottom":
      startX = item1.width / 2 + item1.left;
      startY = item1.height + item1.top;
      break;
    case "left":
      startX = item1.left;
      startY = item1.width / 2 + item1.top;
      break;
    default:
      // invalid input
  }
  
  switch (endPosition) {
    case "top":
      angle= 1.5
      endX = item2.width / 2 + item2.left;
      endY = item2.top;
      break;
    case "right":
      angle=3.14
      endX = item2.width + item2.left;
      endY = item2.height / 2 + item2.top;
      break;
    case "bottom":
      angle = -1.57
      endX = item2.width / 2 + item2.left;
      endY = item2.height + item2.top;
      break;
    case "left":
      angle= 0
      endX = item2.left;
      endY = item2.height / 2 + item2.top;
      break;
    default:
      // invalid input
  }
  
  ctx.moveTo(startX, startY);
  if (startPosition === "bottom" || startPosition === "top") {
    ctx.lineTo(startX, endY);
    //ctx.lineTo(tox, toy);
    //ctx.lineTo(tox - headlen * Math.cos(angle - Math.PI / 6), toy - headlen * Math.sin(angle - Math.PI / 6));
    //ctx.moveTo(tox, toy);
    //ctx.lineTo(tox - headlen * Math.cos(angle + Math.PI / 6), toy - headlen * Math.sin(angle + Math.PI / 6));
  } else {
    ctx.lineTo(endX, startY);
  }
  ctx.lineTo(endX, endY);
  ctx.stroke();
  
  // triangle
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.lineTo(endX, endY);
  ctx.lineTo(endX - head_len * Math.cos(angle - head_angle), endY - head_len * Math.sin(angle - head_angle));
  ctx.lineTo(endX - head_len * Math.cos(angle + head_angle), endY - head_len * Math.sin(angle + head_angle));
  ctx.closePath();
  ctx.fill();
  ctx.restore();
}
