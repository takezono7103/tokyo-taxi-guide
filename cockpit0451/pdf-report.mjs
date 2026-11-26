import {extractCells,collectCells,numbersOnly,summaryImage} from './pdf-grid.mjs';

const columns=['区分','No','開始','終了','迎','開始地点','終了地点','営業km','現金','未収','ETC','人員','備考'];
const headers=['乗務日','日報行順','区分','No','開始日時JST','終了日時JST','迎コード','開始地点',
 '終了地点','営業距離km','現金円','未収円','ETC円','日報人員','備考','迎C調整円',
 '通常乗車税込金額円','休憩分','日報税込収入円','日報税抜営収円','日報出庫時刻','日報帰庫時刻','日報実車率','日報休憩合計分'];
const kinds=['実車','迎C','休','回'];
const text=value=>value.normalize('NFKC').trim();
const digits=value=>text(value).replace(/\D/g,'');
function readClock(value) {
  const part=digits(text(value).replace(/[Oo]/g,'0').replace(/[ilI]/g,'1'));
  if(!/^\d{3,4}$/.test(part)) return '';
  const code=part.padStart(4,'0');
  return /^(?:[01]\d|2[0-3])[0-5]\d$/.test(code)?code.slice(0,2)+':'+code.slice(2):'';
}
function amount(a,b) {
  const parse=value=>/^\d{1,3}(?:[.,]\d{3})*$|^\d+$/.test(text(value))?digits(value):'';
  return parse(a)||parse(b);
}
export function mergePage(japanese,numeric) {
  const rows = japanese.flatMap((line,index)=>{
    const [id,start,end,code,from,to,km,cash,unpaid,etc,people,notes]=line.map(text);
    const n=numeric[index];
    if(![start,end,from,to,n[1]].some(value=>/[0-9一-龯]/.test(value))) return [];
    if(!/[0-9]/.test(start+end+n[1]+n[2])&&!/[一-龯]/.test(from+to)) return [];
    const number=id.match(/^\d{1,2}(?!\d)/)?.[0]??'';
    const kind=/迎[CＣ]/i.test(notes)?'迎C':number?'実車':/回/.test(id)?'回':/休|体/.test(id)?'休':'';
    const distance=km.replace(/[^\d.]/g,'');
    const normalizedKm=/^\d+\.\d$/.test(distance)?distance:
      /^\d{2,3}$/.test(distance)?distance.slice(0,-1)+'.'+distance.at(-1):'';
    const paired=digits(n[1]);
    const numericStart=paired.length===8&&!n[2]?paired.slice(0,4):n[1];
    const numericEnd=paired.length===8&&!n[2]?paired.slice(4):n[2];
    const timeCandidates=(first,second)=>[readClock(first),readClock(second)].find(Boolean)||'';
    return [[kind,number,timeCandidates(start,numericStart),timeCandidates(end,numericEnd),code,from,to,
      normalizedKm,amount(cash,n[7]),amount(unpaid,n[8]),amount(etc,n[9]),amount(people,n[10]),notes]];
  });
  while(rows.length && !rows.at(-1).slice(0,4).some(Boolean)) rows.pop();
  return rows;
}

export function parseSummary(tsv) {
  const parts=[[],[],[]];
  for(const line of tsv.split('\n')){
    const cells=line.split('\t');
    if(cells[0]!=='5'||!cells[11]?.trim())continue;
    const left=Number(cells[6]);
    parts[left<220?0:left<410?1:2].push(cells[11]);
  }
  const date=parts[0].join('').match(/(20\d\d)[/.-](\d{1,2})[/.-](\d{1,2})/);
  return {date:date?date.slice(1).map((part,index)=>index?part.padStart(2,'0'):part).join('-'):'',
    departure:readClock(parts[1].join('')), paper:digits(parts[2].join(''))};
}

export function parseExtraSummary(key,raw){
 const v=text(raw).replace(/\s/g,'');
 if(key==='arrival')return /^\d{1,2}:\d{2}$/.test(v)?readClock(v):'';
 if(key==='net')return /^(?:\d{1,3}(?:,\d{3})+|\d{1,8})$/.test(v)?digits(v):'';
 if(key==='rate'){const m=v.match(/^(\d{1,3}\.\d)%?$/);return m&&Number(m[1])<=100?m[1]:'';}
 if(key==='restTotal'){const m=v.match(/^(\d{1,2}):([0-5]\d)$/);return m?String(Number(m[1])*60+Number(m[2])):'';}
 return '';
}
const csvCell=value=>{
  const raw=String(value??'');
  const safe=/^[=+@\t\r]|^-(?!\d+$)/.test(raw)?"'"+raw:raw;
  return /[",\r\n]/.test(safe)?'"'+safe.replaceAll('"','""')+'"':safe;
};

export function makeCsv({date,departure,paper,net='',arrival='',rate='',restTotal=''},rows) {
  const errors=[];
  if(!/^\d{4}-\d{2}-\d{2}$/.test(date)||!Number.isFinite(Date.parse(date))||
    new Date(date).toISOString().slice(0,10)!==date) errors.push('乗務日を確認してください。');
  if(!/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(departure)) errors.push('出庫時刻を確認してください。');
  if(!/^\d{1,8}$/.test(paper)) errors.push('日報の税込収入を確認してください。');
  if(net!==''&&(!/^\d{1,8}$/.test(net)||Number(net)>Number(paper)))errors.push('税抜営収を確認してください。');
  if(arrival!==''&&readClock(arrival)!==arrival)errors.push('帰庫時刻を確認してください。');
  if(rate!==''&&(!/^\d{1,3}(?:\.\d)?$/.test(rate)||Number(rate)>100))errors.push('実車率を確認してください。');
  if(restTotal!==''&&(!/^\d{1,4}$/.test(restTotal)||Number(restTotal)>2880))errors.push('日報休憩合計を確認してください。');
  if(!rows.length) errors.push('明細を1行以上入力してください。');
  if(errors.length)return {errors};
  const dayAfter=new Date(Date.parse(date)+86400000).toISOString().slice(0,10);
  const timestamp=value=>(value<departure?dayAfter:date)+'T'+value+':00+09:00';
  let lastNumber=0, subtotal=0, rest=0, cancellations=0;
  const records=rows.map((row,index)=>{
    const [kind,no,start,end,code,from,to,km,cash,credit,etc,people,notes]=row.map(text);
    const ride=kind==='実車'||kind==='迎C';
    const startValid=readClock(start)===start&&!!start;
    const endValid=readClock(end)===end&&!!end;
    const startAt=timestamp(start),endAt=timestamp(end);
    if(!kinds.includes(kind)||!startValid||!endValid||endAt<startAt||!from||
        (ride&&(!to||!/^\d+(?:\.\d+)?$/.test(km)||
          ![cash,credit,etc,people].every(value=>/^\d{1,8}$/.test(value))))) {
      errors.push('明細 '+(index+1)+'行目の区分・時刻・地点・数値を確認してください。');
    }
    if(ride){
      if(!/^\d+$/.test(no)||Number(no)!==lastNumber+1)
        errors.push('明細 '+(index+1)+'行目のNoが連番になっていません。');
      lastNumber=Number(no)||lastNumber;
    }
    const gross=ride?Number(cash)+Number(credit):0;
    const canceled=kind==='迎C'?gross:0;
    const minutes=kind==='休'?(Date.parse(endAt)-Date.parse(startAt))/60000:'';
    if(kind==='迎C')cancellations++;
    subtotal+=gross;
    rest+=Number(minutes);
    return [date,index+1,kind,ride?no:'',startAt,endAt,code,from,to,ride?km:'',ride?cash:'',
      ride?credit:'',ride?etc:'',ride?people:'',notes,ride?-canceled:'',ride?gross-canceled:'',
      minutes,index===0?paper:'',index===0?net:'',index===0?departure:'',index===0?arrival:'',index===0?rate:'',index===0?restTotal:''];
  });
  if(restTotal!==''&&Number(restTotal)!==rest)errors.push('日報休憩合計と明細休憩合計が一致しません。');
  return {errors,subtotal,rest,cancellations,number:lastNumber,
    csv:[headers,...records].map(row=>row.map(csvCell).join(',')).join('\r\n')+'\r\n'};
}

const byId=id=>document.getElementById(id);
const canvas=(width,height)=>Object.assign(document.createElement('canvas'),{width,height});
const form=typeof document==='undefined'?null:byId('pdf-review');
let selectedFile=null,originalUrl=null,busy=false;
let rows=[];
function editRow(values) {
  const row=document.createElement('tr');
  rows.push(row);
  values.forEach((value,index)=>{
    const td=document.createElement('td');
    const control=document.createElement(index===0?'select':'input');
    if(index===0)control.replaceChildren(...['',...kinds].map(kind=>new Option(kind||'確認',kind)));
    else{
      control.type='text';
      control.size=index===5||index===6||index===12?15:6;
      if([1,7,8,9,10,11].includes(index))control.inputMode=index===7?'decimal':'numeric';
    }
    control.value=value;
    control.setAttribute('aria-label',columns[index]);
    td.append(control);row.append(td);
  });
  const cell=document.createElement('td'), remove=document.createElement('button');
  remove.type='button';remove.textContent='削除';
  remove.addEventListener('click',()=>{
    rows=rows.filter(item=>item!==row);
    row.remove();
    invalidate();
  });
  cell.append(remove);row.append(cell);
  byId('pdf-rows').append(row);
}
function invalidate() {
  byId('pdf-confirm').checked=false;
  byId('pdf-save-status').textContent='';
  byId('pdf-check-result').textContent='';
}
function getReview() {
  const info={date:byId('pdf-date').value,departure:byId('pdf-departure').value,paper:byId('pdf-paper').value,net:byId('pdf-net').value,arrival:byId('pdf-arrival').value,rate:byId('pdf-rate').value,restTotal:byId('pdf-rest-total').value};
  const values=rows.map(row=>[...row.querySelectorAll('input,select')].map(input=>input.value));
  return {info,values};
}
function refreshReview() {
  const {info,values}=getReview();
  const result=makeCsv(info,values);
  const status=byId('pdf-check-result');
  if(result.errors.length){
    status.textContent=result.errors.join('\n');
    return null;
  }
  const message='通常乗車 '+(result.number-result.cancellations)+'件、迎車キャンセル '+result.cancellations+
    '件、休憩 '+result.rest+'分。明細の現金＋未収 '+result.subtotal.toLocaleString('ja-JP')+'円。';
  const mismatch=result.subtotal!==Number(info.paper);
  status.textContent=message+(mismatch?' 日報の税込収入と差があります。原本を確認し、差が正しければ下のチェックを付けてください。':'');
  return result.csv;
}
async function recognize(file) {
  const pdfjs=await import('./ocr/pdf.min.mjs');
  pdfjs.GlobalWorkerOptions.workerSrc=new URL('./ocr/pdf.worker.min.mjs',import.meta.url).href;
  const pdf=await pdfjs.getDocument({data:await file.arrayBuffer(),isEvalSupported:false}).promise;
  try {
    if(pdf.numPages<1||pdf.numPages>4)throw new Error('1乗務分の日報PDF（4ページ以内）を選んでください。');
    const options={
      workerPath:new URL('./ocr/worker.min.js',import.meta.url).href,
      corePath:new URL('./ocr/tesseract-core-lstm.wasm.js',import.meta.url).href,
      langPath:new URL('./ocr/',import.meta.url).href,
      cacheMethod:'none',workerBlobURL:false
    };
    const worker=await window.Tesseract.createWorker('jpn',1,options);
    try {
      let summary=null;
      const extracted=[];
      for(let number=1;number<=pdf.numPages;number++){
        byId('pdf-status').textContent='ページ '+number+' / '+pdf.numPages+' を読み取り中…';
        const page=await pdf.getPage(number);
        const base=page.getViewport({scale:1});
        if(base.height<base.width||base.width/base.height<.64||base.width/base.height>.76)
          throw new Error('縦向きの日報PDFを選んでください。');
        const viewport=page.getViewport({scale:2600/base.height});
        const rendered=canvas(Math.ceil(viewport.width),Math.ceil(viewport.height));
        await page.render({canvasContext:rendered.getContext('2d'),canvas:rendered,viewport}).promise;
        const layout=extractCells(rendered,number===1,canvas);
        await worker.setParameters({tessedit_pageseg_mode:'6',tessedit_char_whitelist:''});
        const japanese=collectCells((await worker.recognize(layout.canvas,{}, {tsv:true})).data.tsv,layout);
        await worker.reinitialize('eng');
        await worker.setParameters({tessedit_pageseg_mode:'6',tessedit_char_whitelist:'0123456789:.,'});
        const numeric=collectCells((await worker.recognize(numbersOnly(layout,canvas),{}, {tsv:true})).data.tsv,layout);
        if(number===1){
          await worker.setParameters({tessedit_pageseg_mode:'11',tessedit_char_whitelist:'0123456789/:.,-'});
          summary=parseSummary((await worker.recognize(summaryImage(rendered,canvas),{}, {tsv:true})).data.tsv);
          // Numeric cells on the same report form; do not infer a missing value.
          await worker.setParameters({tessedit_pageseg_mode:'7',tessedit_char_whitelist:'0123456789:,.%'});
          for(const [key,x,y,w,h] of [['arrival',1050,200,128,49],['net',1228,350,99,26],['rate',1228,469,99,26],['restTotal',1228,503,99,24]]){
            const c=canvas(w*3,h*3),ctx=c.getContext('2d');
            ctx.drawImage(rendered,x/1409*rendered.width,y/2000*rendered.height,w/1409*rendered.width,h/2000*rendered.height,0,0,c.width,c.height);
            const raw=(await worker.recognize(c)).data.text.trim();
            summary[key]=parseExtraSummary(key,raw);c.width=1;
          }
        }
        extracted.push(...mergePage(japanese,numeric));
        for(const image of [rendered,layout.canvas]) image.width=1;
        if(number<pdf.numPages)await worker.reinitialize('jpn');
      }
      if(!extracted.length)throw new Error('日報の明細を読み取れませんでした。');
      return {summary,extracted};
    }finally{await worker.terminate();}
  }finally{await pdf.destroy();}
}

if(form){
  byId('pdf-file').addEventListener('change',()=>{
    selectedFile=byId('pdf-file').files[0]??null;
    form.hidden=true;
    invalidate();
    if(originalUrl)URL.revokeObjectURL(originalUrl);
    originalUrl=selectedFile?URL.createObjectURL(selectedFile):null;
    byId('pdf-original').href=originalUrl??'#';
    byId('pdf-start').disabled=!selectedFile;
    byId('pdf-status').textContent='';
  });
  byId('pdf-start').addEventListener('click',async()=>{
    if(!selectedFile||busy)return;
    busy=true;
    form.hidden=true;
    invalidate();
    const fileInput=byId('pdf-file'), start=byId('pdf-start'), status=byId('pdf-status');
    fileInput.disabled=start.disabled=true;
    status.textContent='OCRを準備しています…';
    try {
      const {summary,extracted}=await recognize(selectedFile);
      byId('pdf-rows').replaceChildren();
      rows=[];
      byId('pdf-date').value=summary.date;
      byId('pdf-departure').value=summary.departure;
      byId('pdf-paper').value=summary.paper;
      for(const [id,key] of [['pdf-net','net'],['pdf-arrival','arrival'],['pdf-rate','rate'],['pdf-rest-total','restTotal']])byId(id).value=summary[key]||'';
      byId('pdf-confirm').checked=false;
      extracted.forEach(editRow);
      form.hidden=false;
      status.textContent=rows.length+'行を読み取りました。原本と照合してからCSVを保存してください。';
    }catch(error){
      status.textContent='PDFを読み取れませんでした。'+error.message;
    }finally{
      busy=false;
      fileInput.disabled=start.disabled=false;
    }
  });
  form.addEventListener('input',event=>{
    if(event.target.id==='pdf-confirm')return;
    byId('pdf-confirm').checked=false;
    invalidate();
  });
  byId('pdf-add').addEventListener('click',()=>{editRow(columns.map(()=>''));invalidate();});
  byId('pdf-check').addEventListener('click',refreshReview);
  function confirmedCsv(){
    const csv=refreshReview();
    const status=byId('pdf-save-status');
    if(!csv){
      status.textContent='上の検算結果を確認してください。修正前のデータは「OCR下書きCSVを保存」から出力できます。';
      return;
    }
    if(!byId('pdf-confirm').checked){
      status.textContent='原本を確認し、「原本と読み取り結果を照合しました」にチェックを付けてください。';
      return;
    }
    return csv;
  }
  byId('pdf-save').addEventListener('click',()=>{
    const csv=confirmedCsv();
    if(!csv)return;
    const date=byId('pdf-date').value.slice(2).replaceAll('-','');
    saveCsv(csv,'DR'+date+'.csv');
  });
  byId('pdf-apply').addEventListener('click',()=>{
    const csv=confirmedCsv();
    if(!csv)return;
    document.dispatchEvent(new CustomEvent('taxi:confirmed-report-v0451',{detail:{csv}}));
    byId('pdf-save-status').textContent='明細を締め集計に反映しました。';
  });
  byId('pdf-draft').addEventListener('click',()=>{
    const {info,values}=getReview();
    const draft=makeDraftCsv(info,values);
    const basename=selectedFile.name.replace(/\.pdf$/i,'');
    saveCsv(draft,basename+'_OCR下書き.csv');
  });
}

export function makeDraftCsv(info,values) {
  const draftRows=[['OCR下書き','乗務日','出庫時刻','日報税込収入（OCR値）'],
    ['原本照合前',info.date,info.departure,info.paper],[],['明細行',...columns],
    ...values.map((row,index)=>[index+1,...row])];
  return draftRows.map(row=>row.map(csvCell).join(',')).join('\r\n')+'\r\n';
}

async function saveCsv(csv,filename) {
  const status=byId('pdf-save-status');
  const blob=new Blob(['\uFEFF',csv],{type:'text/csv;charset=utf-8'});
  const file=new File([blob],filename,{type:'text/csv'});
  if(navigator.canShare?.({files:[file]})){
    try {
      await navigator.share({files:[file]});
      status.textContent='共有メニューで選択した場所をご確認ください。';
      return;
    }catch(error){
      if(error.name==='AbortError'){
        status.textContent='保存をキャンセルしました。Safariでは共有メニューから「ファイルに保存」を選べます。';
        return;
      }
    }
  }
  const url=URL.createObjectURL(blob);
  const link=document.createElement('a');
  link.href=url;
  link.download=filename;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(()=>URL.revokeObjectURL(url),60000);
  status.textContent='ダウンロードを開始しました。Safariのダウンロード一覧をご確認ください。';
}
