const layouts = [
  {width:1409, start:848, step:33.1, capacity:31,
   columns:[88,124,183,242,275,515,755,817,896,976,1055,1102,1332],
   bottom:[90,124,181,238,272,513,756,819,902,982,1063,1108,1340]},
  {width:1404, start:273, step:34.2, capacity:46,
   columns:[102,137,195,252,285,528,770,834,914,995,1073,1122,1355],
   bottom:[123,153,209,265,300,528,753,815,891,971,1045,1097,1320]}
];

export function extractCells(source, first, makeCanvas) {
  const layout = layouts[first ? 0 : 1];
  const {columns,bottom,capacity}=layout;
  const ctx=source.getContext('2d'), w=source.width,h=source.height;
  const pixels=ctx.getImageData(0,0,w,h).data;
  const sx=w/layout.width,sy=h/2000;
  const dark=(x,y,threshold=145)=>pixels[(Math.round(y*sy)*w+Math.round(x*sx))*4]<threshold;
  const guessY=(index,x)=>layout.start+layout.step*index+
    (first ? index*index*.005 + (x-620)*(-.012-index*.00023) : Math.min(0,(x-650)*.011));
  function horizontal(index,x) {
    const guess=guessY(index,x);
    let best=Math.round(guess), score=-Infinity;
    for(let y=Math.round(guess)-10;y<=guess+10;y++){
      let hits=0;
      for(let dx=-22;dx<=22;dx+=2) if(dark(x+dx,y)) hits++;
      const rating=hits-Math.abs(y-guess)*.35;
      if(rating>score){score=rating;best=y;}
    }
    return best;
  }
  function vertical(index,col) {
    const guess=columns[col]+(bottom[col]-columns[col])*index/(capacity+1);
    const y=guessY(index+.5,guess);
    let best=Math.round(guess),score=-Infinity;
    for(let x=Math.round(guess)-10;x<=guess+10;x++){
      let hits=0;
      for(let dy=-13;dy<=13;dy++) if(dark(x,y+dy)) hits++;
      const rating=hits-Math.abs(x-guess)*.23;
      if(rating>score){score=rating;best=x;}
    }
    return best;
  }
  const rects=[];
  for(let row=1;row<=capacity;row++){
    const boundaries=columns.map((_,col)=>vertical(row,col));
    const cells=columns.slice(0,-1).map((_,col)=>{
      const left=boundaries[col]+3,right=boundaries[col+1]-3;
      const mid=(left+right)/2;
      return {left,right,top:horizontal(row,mid)+4,bottom:horizontal(row+1,mid)-4};
    });
    const time=cells[1];
    let ink=0;
    for(let y=time.top+3;y<time.bottom-3;y++)
      for(let x=time.left+5;x<time.right-5;x++) if(dark(x,y,115)) ink++;
    if(first || ink>=24) rects.push(cells);
  }
  const widths=[85,125,125,95,415,415,125,155,155,155,105,450];
  const offsets=widths.map((_,i)=>widths.slice(0,i).reduce((a,b)=>a+b,0));
  const canvas=makeCanvas(widths.reduce((a,b)=>a+b,0),Math.max(1,rects.length)*54);
  const out=canvas.getContext('2d'), image=out.createImageData(canvas.width,canvas.height);
  image.data.fill(255);
  rects.forEach((cells,index)=>{
    cells.forEach(({left,right,top,bottom},col)=>{
      const span=Math.round((right-left)*1.55);
      const depth=Math.min(42,Math.round((bottom-top)*1.55));
      const rows=Array.from({length:Math.max(0,depth)},(_,y)=>
        Array.from({length:Math.max(0,span)},(_,x)=>dark(left+x/1.55,top+y/1.55,160)));
      const verticalInk=Array.from({length:Math.max(0,span)},(_,x)=>rows.filter(row=>row[x]).length);
      rows.forEach((line,y)=>{
        if(line.filter(Boolean).length>span*.73)return;
        line.forEach((ink,x)=>{
          if(!ink||verticalInk[x]>depth*.82)return;
          const target=((index*54+Math.floor((54-depth)/2)+y)*canvas.width+offsets[col]+7+x)*4;
          image.data[target]=image.data[target+1]=image.data[target+2]=0;
        });
      });
    });
  });
  out.putImageData(image,0,0);
  return {canvas,offsets,count:rects.length};
}

export function collectCells(tsv, layout) {
  const rows=Array.from({length:layout.count},()=>Array.from({length:12},()=>''));
  for(const line of tsv.split('\n')){
    const fields=line.split('\t');
    if(fields[0]!=='5'||!fields[11]?.trim()) continue;
    const x=Number(fields[6]), center=Number(fields[7])+Number(fields[9])/2;
    const row=rows[Math.floor(center/54)];
    const col=layout.offsets.findLastIndex(offset=>offset<=x);
    if(row&&col>=0) row[col]+=fields.slice(11).join('\t').trim();
  }
  return rows;
}

export function numbersOnly(layout, makeCanvas) {
  const {canvas, offsets}=layout;
  const copy=makeCanvas(canvas.width,canvas.height);
  const context=copy.getContext('2d');
  context.fillStyle='#fff';
  context.fillRect(0,0,copy.width,copy.height);
  for(const [x,end] of [[offsets[1],offsets[3]],[offsets[6],offsets[11]]]){
    context.drawImage(canvas,x,0,end-x,canvas.height,x,0,end-x,canvas.height);
  }
  return copy;
}

export function summaryImage(source, makeCanvas) {
  const canvas=makeCanvas(580,90), ctx=canvas.getContext('2d');
  ctx.fillStyle='#fff'; ctx.fillRect(0,0,580,90);
  for(const [x,y,w,h,to] of [[101,207,138,36,15],[949,200,91,40,242],[1242,258,89,25,425]]){
    ctx.drawImage(source,x/1409*source.width,y/2000*source.height,
      w/1409*source.width,h/2000*source.height,to,12,w*1.45,h*1.45);
  }
  return canvas;
}
