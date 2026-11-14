const fs=require('fs');const {parse}=require('@babel/parser');const traverse=require('@babel/traverse').default;
const ast=parse(fs.readFileSync('src/App.js','utf8'),{sourceType:'module',plugins:['jsx'],errorRecovery:true});
const out={};
traverse(ast,{VariableDeclarator(p){ if(p.node.id.name!=='_traductionsApp')return;
  p.node.init.properties.forEach(l=>{const n=l.key.name||l.key.value; out[n]={}; l.value.properties.forEach(kv=>{ if(kv.value.type==='StringLiteral') out[n][kv.key.name||kv.key.value]=kv.value.value;});});}});
fs.writeFileSync('/tmp/app_dict.json',JSON.stringify(out));
const fr=out.fr; const ks=Object.keys(fr);
console.log('cles fr locales :',ks.length,'| en:',Object.keys(out.en).length,'| de:',Object.keys(out.de).length);
