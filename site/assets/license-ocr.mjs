// Private documents are processed in this browser, using only self-hosted assets.
const VENDOR='/vendor/license-ocr-20261007';
const alphabet='0123456789ABCDEFGHJKLMNPQRTUWXY';
const weights=[1,3,9,27,19,26,16,17,20,29,25,13,8,24,10,30,28];
export function validCreditCode(code){
  if(!/^[0-9A-HJ-NPQRTUWXY]{18}$/.test(code))return false;
  return alphabet[(31-weights.reduce((sum,w,i)=>sum+w*alphabet.indexOf(code[i]),0)%31)%31]===code[17];
}
export function parseLicenseFields(raw){
  const text=String(raw||'').normalize('NFKC').replace(/\r/g,'').replace(/([\u3400-\u9fff])[^\S\n]+(?=[\u3400-\u9fff])/g,'$1');
  const lines=text.split('\n').map(l=>l.trim()).filter(Boolean),result={};
  const boundary=/(?:统一社会信用|注册号|登记机关|法定代表人|经营范围|经营者|注册资本|成立日期|营业期限|类\s*型|住\s*所|地\s*址|名\s*称|Nature of Business|Business Registration|Date of|Certificate No)/i;
  const valueAfter=(label,max)=>{
    for(let i=0;i<lines.length;i++){
      const match=lines[i].match(label);if(!match)continue;
      let value=lines[i].slice(match.index+match[0].length).replace(/^\s*[:：]\s*/,'').trim();
      if(!value&&lines[i+1]&&!boundary.test(lines[i+1]))value=lines[i+1];
      else if(value&&max===320&&lines[i+1]&&!boundary.test(lines[i+1])&&!/营业执照|Business Registration Certificate/i.test(lines[i+1]))value+=' '+lines[i+1];
      value=value.split(boundary)[0].trim();
      if(value.length>=2&&value.length<=max)return value;
    }
    return '';
  };
  const company=valueAfter(/(?:公司名称|企业名称|名\s*称|(?:Company|Business)\s+Name|Name\s+of\s+(?:Company|Business|Corporation))\s*[:：]?/i,160);
  if(company)result.companyName=company;
  const address=valueAfter(/(?:注册(?:地址|住所)|住\s*所|(?:Registered|Business)\s+Address|Address\s+of\s+(?:Business|Company))\s*[:：]?/i,320);
  if(address)result.address=address;
  const label=text.match(/(?:统一社会信用(?:代码|号码))\s*[:：]?\s*([0-9A-HJ-NPQRTUWXY\s]{18,40})/i);
  const candidates=label?[label[1].replace(/\s/g,'').slice(0,18).toUpperCase()]:text.match(/\b[0-9A-HJ-NPQRTUWXY]{18}\b/gi)||[];
  const credit=candidates.find(validCreditCode);if(credit)result.registrationNo=credit.toUpperCase();
  if(!credit){const registration=valueAfter(/(?:商业登记(?:证)?号码|商業登記(?:證)?號碼|Registration\s+(?:No\.?|Number)|Business\s+Registration\s+(?:No\.?|Number))\s*[:：]?/i,100);if(registration&&/^\d[\d\s/-]{5,30}$/.test(registration))result.registrationNo=registration;}
  return result;
}
export function applyLicenseFields(form,fields,replaceCompanyDefault=false){
  const applied=[];
  for(const name of ['companyName','registrationNo','address']){
    const input=form?.elements?.[name],value=fields[name];
    if(input&&value&&(!input.value.trim()||name==='companyName'&&replaceCompanyDefault&&input.value===input.defaultValue)){
      input.value=value;input.dispatchEvent(new Event('input',{bubbles:true}));applied.push(name);
    }
  }
  return applied;
}
async function imageForOCR(file){
  const bitmap=await createImageBitmap(file);
  try{
    if(bitmap.width*bitmap.height>25000000)throw Error('Image is too large to recognize.');
    const scale=Math.min(1,2600/Math.max(bitmap.width,bitmap.height));
    const canvas=document.createElement('canvas');canvas.width=Math.round(bitmap.width*scale);canvas.height=Math.round(bitmap.height*scale);
    canvas.getContext('2d').drawImage(bitmap,0,0,canvas.width,canvas.height);return canvas;
  }finally{bitmap.close();}
}
export async function recognizeLicense(file,onProgress=()=>{}){
  let worker,pdf,pdfTask;
  try{
    let text='',pictures=[];
    if(file.type==='application/pdf'||/\.pdf$/i.test(file.name)){
      onProgress(0);
      const lib=await import(VENDOR+'/pdf.mjs');lib.GlobalWorkerOptions.workerSrc=VENDOR+'/pdf.worker.mjs';
      pdfTask=lib.getDocument({data:new Uint8Array(await file.arrayBuffer()),isEvalSupported:false,useSystemFonts:true,disableFontFace:true,enableXfa:false});pdf=await pdfTask.promise;
      const pages=[];
      for(let i=1;i<=Math.min(pdf.numPages,2);i++){const page=await pdf.getPage(i);pages.push(page);const content=await page.getTextContent();let y;
        for(const item of content.items){if(!('str' in item))continue;if(y!==undefined&&Math.abs(item.transform[5]-y)>3)text+='\n';text+=item.str+' ';y=item.transform[5];if(item.hasEOL)text+='\n';}text+='\n';}
      const direct=parseLicenseFields(text);if(direct.companyName&&direct.registrationNo&&direct.address){onProgress(1);return direct;}
      for(const page of pages){const initial=page.getViewport({scale:1}),scale=Math.min(2,2600/Math.max(initial.width,initial.height)),viewport=page.getViewport({scale});const canvas=document.createElement('canvas');canvas.width=Math.ceil(viewport.width);canvas.height=Math.ceil(viewport.height);await page.render({canvasContext:canvas.getContext('2d'),viewport}).promise;pictures.push(canvas);}
    }else pictures=[await imageForOCR(file)];
    const {default:{createWorker}}=await import(VENDOR+'/tesseract.esm.min.js');
    worker=await createWorker(['chi_sim','eng'],1,{workerPath:VENDOR+'/worker.min.js',corePath:VENDOR+'/core',langPath:VENDOR+'/lang',cacheMethod:'none',logger:message=>onProgress(message.status==='recognizing text'?0.2+0.75*(message.progress||0):0.05)});
    for(const picture of pictures){const result=await worker.recognize(picture);text+='\n'+result.data.text;picture.width=1;picture.height=1;}
    onProgress(1);return parseLicenseFields(text);
  }finally{if(worker)await worker.terminate();if(pdfTask)await pdfTask.destroy();}
}
