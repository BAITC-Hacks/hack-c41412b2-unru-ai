const {readFileSync}=require('node:fs');
const {runInNewContext}=require('node:vm');
const assert=require('node:assert/strict');
class Element {
 constructor(){this.children=[];this.attrs={};this.events={};this.hidden=false;}
 append(...nodes){for(const n of nodes){if(n.parent)n.parent.children=n.parent.children.filter(x=>x!==n);this.children.push(n);n.parent=this;}}
 setAttribute(k,v){this.attrs[k]=v;}
 addEventListener(k,v){this.events[k]=v;}
 querySelectorAll(s){const found=[];for(const c of this.children){if(s.startsWith('#')?c.id===s.slice(1):c.attrs.role===s.slice(6,-1))found.push(c);found.push(...c.querySelectorAll(s));}return found;}
 querySelector(s){return this.querySelectorAll(s)[0];}
 cloneNode(){const n=new Element();n.textContent=this.textContent;return n;}
 click(){this.events.click();} focus(){this.focused=true;}
}
const card=new Element(),parts=Array.from({length:15},(_,i)=>{const e=new Element();e.textContent='original '+i;return e;});card.append(...parts);
const source=readFileSync('web/app.js','utf8'),fn=source.slice(source.indexOf('function organizeInspector('),source.indexOf("const NS="));
const context={$:()=>card,document:{createElement:()=>new Element()}};runInNewContext(fn,context);context.organizeInspector();
const tabs=card.querySelectorAll('[role=tab]'),panels=card.querySelectorAll('[role=tabpanel]');
assert.equal(tabs.length,5);assert.equal(panels.filter(p=>!p.hidden).length,1);assert.equal(card.children[0],parts[0]);
assert.equal(panels.flatMap(p=>p.children).filter(c=>parts.includes(c)).length,14);
console.log('Inspector: every original section retained exactly once');
tabs[2].click();assert.equal(panels[2].hidden,false);assert.equal(panels.filter(p=>!p.hidden).length,1);assert.equal(tabs[2].attrs['aria-selected'],'true');
console.log('Inspector: tab switching exposes exactly one panel');
tabs[2].events.keydown({key:'End',preventDefault(){}});assert.equal(tabs[4].focused,true);assert.equal(panels[4].hidden,false);
console.log('Inspector: keyboard navigation and focus work');
assert.equal(panels[0].children.at(-1),parts[14]);assert.equal(panels[4].children.at(-1).textContent,parts[14].textContent);assert.notEqual(panels[4].children.at(-1),parts[14]);
console.log('Inspector: next request retained in overview and copied to data');
