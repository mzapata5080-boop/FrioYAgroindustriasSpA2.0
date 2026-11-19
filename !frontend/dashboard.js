'use strict';
function goHome() {
 loadVersion++;
 $('dashboard').hidden=false; $('module-view').hidden=true; $('editor').hidden=true;
 $('notice').replaceChildren(); current='';
}
function openModule(resource) { load(resource).catch(e=>notice(e.message,true)); }
function action(resource, label, cls='btn-outline-success', create=false) {
 const button=node('button',label,`btn ${cls}`);
 button.type='button';
 button.onclick=async()=>{try{await load(resource);if(create && current===resource && metadata.can_write)showForm(metadata.fields);}catch(e){notice(e.message,true);}};
 return button;
}
function roleCard(title, description, feature, cls, buttons) {
 const card=node('section',undefined,`card role-card ${cls}`);
 card.append(node('h2',title),node('hr'),node('p',description,'role-description'),node('p',feature,'role-feature'));
 const actions=node('div',undefined,'role-actions');buttons.forEach(b=>actions.append(b));card.append(actions);
 return card;
}
function renderSession() {
 $('login-panel').hidden=!!user; $('workspace').hidden=!user; $('logout').hidden=!user;
 $('identity').textContent=user?`Bienvenido, ${user.username}`:'';
 $('editor').hidden=true; $('records').replaceChildren(); $('new').hidden=true; $('modules').replaceChildren();
 $('role-cards').replaceChildren(); $('warehouse-actions').replaceChildren(); $('additional-actions').replaceChildren();
 $('additional-modules').hidden=true; $('additional-modules').open=false;
 if(!user)return;
 const can=roles=>user.is_superuser||roles.includes(user.rol);
 const fullName=(user.name||'').trim();
 $('welcome').textContent=fullName?`Bienvenido, ${fullName}`:'Bienvenido,';
 if(can(['gerencia'])) {
  $('role-cards').append(roleCard('Administración y Gerencia','Módulo de gestión de personal','Agregar nuevos trabajadores y asignar roles','management-card',[
   action('trabajadores','Gestionar Trabajadores','btn-primary'),action('kardex','Ver Kardex','btn-kardex')
  ]));
 }
 const financeButtons=()=>[
  action('proveedores','Gestión de Proveedores','btn-warning'),
  action('clientes','Administración de Clientes','btn-outline-warning'),
  action('facturas','Facturas de Compra','btn-outline-warning')
 ];
 if(user.rol==='finanzas'){
  $('role-cards').append(roleCard('Administrativo y Finanzas','Módulo de gestión comercial','Administrar proveedores, clientes y facturas','finance-card',financeButtons()));
 } else if(can(['gerencia'])) {
  $('additional-modules').hidden=false;financeButtons().forEach(b=>$('additional-actions').append(b));
 }
 $('warehouse-actions').append(action('articulos','Abrir inventario'));
 if(user.rol==='bodega') {
  $('warehouse-actions').append(action('articulos','Crear artículo','btn-outline-success',true),action('ingresos','Registrar ingreso','btn-success',true),action('categorias','Categorías'),action('ingresos','Ver ingresos'),action('salidas','Ver salidas'));
 }
 for(const [key,title] of Object.entries(names)){
  const visible=key==='articulos'||can(key==='trabajadores'||key==='kardex'?['gerencia']:['clientes','proveedores','facturas'].includes(key)?['gerencia','finanzas']:['bodega','gerencia']);
  if(!visible)continue;
  const b=node('button',title,'btn btn-outline-primary');b.type='button';b.dataset.resource=key;b.onclick=()=>openModule(key);$('modules').append(b);
 }
 goHome();
}
