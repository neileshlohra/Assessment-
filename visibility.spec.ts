import { test, expect } from '@playwright/test';
import path from 'path';
const fixture = `file://${path.resolve(__dirname, '../fixtures/hobby-form.html')}`;
test.describe('schema-driven visibility logic',()=>{
 test('shows hobby text field when q_3 = Yes and hides it for No',async({page})=>{
  await page.goto(fixture); const hobby=page.locator('#q_4'); const container=page.locator('#q_4_container');
  await expect(container).toBeHidden(); await page.selectOption('#q_3',{label:'Yes'}); await expect(hobby).toBeVisible(); await hobby.fill('Football'); await page.selectOption('#q_3',{label:'No'}); await expect(container).toBeHidden();
 });
 test('conditional field follows repeated edits',async({page})=>{await page.goto(fixture);const c=page.locator('#q_4_container');for(const value of ['Yes','No','Yes','No']){await page.selectOption('#q_3',{label:value});if(value==='Yes')await expect(c).toBeVisible();else await expect(c).toBeHidden();}});
});
