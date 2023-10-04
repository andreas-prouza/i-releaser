
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
var flow_button_fokus='';


function connectItems(item1, item2, startPosition, endPosition) {
  let canvas = document.getElementById("flowchart");
  let ctx = canvas.getContext("2d");
  var width = 2;
  var color = 'grey';
  const head_len = 16;
  const head_angle = Math.PI / 6;
  let angle = 0;

  if (item1.id == flow_button_fokus || item2.id == flow_button_fokus) {
    color = 'red';
    width = 4;
  }

  ctx.fillStyle = color;
  ctx.strokeStyle = color;
  ctx.lineJoin = 'red';
  ctx.lineWidth = width;

  canvas_pos = canvas.getBoundingClientRect();
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
  startX = startX - canvas_pos.left;
  startY = startY - canvas_pos.top;
  
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
  
  endX = endX - canvas_pos.left;
  endY = endY - canvas_pos.top;

  ctx.beginPath();
  ctx.moveTo(startX, startY);
  if (startPosition === "bottom" || startPosition === "top") {
    ctx.lineTo(startX, endY);
  } else {
    ctx.lineTo(endX, startY);
  }
  ctx.lineTo(endX, endY);
  ctx.stroke();
  
  // triangle
  ctx.beginPath();
  //ctx.fillStyle = color;
  ctx.moveTo(endX, endY);
  ctx.lineTo(endX - head_len * Math.cos(angle - head_angle), endY - head_len * Math.sin(angle - head_angle));
  ctx.lineTo(endX - head_len * Math.cos(angle + head_angle), endY - head_len * Math.sin(angle + head_angle));
  ctx.closePath();
  ctx.fill();
  
  //ctx.moveTo(0, 0);
  //ctx.lineTo(850, 1450);
  //ctx.stroke();
}
