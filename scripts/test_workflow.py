"""Behavioral regressions for complete article production and invalid handoffs."""
import copy
from pathlib import Path
import tempfile
import unittest
from runtime import digest, read_json, save_json
from project import load
from production import render, verify, finalize, verify_clipboard


class ArticleWorkflow(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.job=self.root/'job'
        self.job.mkdir()
        from PIL import Image
        Image.new('RGB',(600,300),'#e1eee1').save(self.job/'figure.png')
        self.text='''# 工具链验收文章

这是一份用于验证排版和文件衔接的测试材料，不代表真实产品新闻或用户体验。正文保留中文、技术词和必要的上下文，让手机上的读者能够连续阅读。

## 实际检查

这里观察图片是否加载、代码能否原样复制，以及窄屏表格是否让整页横向溢出。测试中的文字不承担事实论证。

![原始测试图片](asset:figure)

```python
path = "C:/任务/正文.md"
print("<tag> & 中文")
```

| 对象 | 检查 |
| --- | --- |
| 中文文章 | 带有很长路径标识的示例 project-with-a-long-identifier.json |
| 图片 | 成品包内的相对路径 |

[链接示例](https://example.org/docs)
'''
        (self.job/'article.md').write_text(self.text,'utf-8')
        self.project={'title':'工具链验收文章','summary':'测试排版、代码和素材衔接。','audience':'测试读者','purpose':'验证成品链路',
                      'approval_status':'direct','research_mode':'none','review_file':'review.json',
                      'platforms':{p:{'file':'article.md'} for p in ('blog','wechat','post')},
                      'assets':[{'id':'figure','path':'figure.png','role':'diagram','rights':{'kind':'owned'}}]}
        self.path=self.job/'project.json'
        self.out=self.root/'delivery'
        self.save()

    def save(self):
        save_json(self.path,self.project)

    def review(self):
        report=read_json(self.out/'report.json')
        save_json(self.job/'review.json',{'status':'reviewed','reviewer':'test fixture, not a human assessment',
            'content_hashes':load(self.path)['hashes'],'findings':[],
            'visual_review':{'render_id':report['render_id'],'screenshots':['qa/top.png'],
                             'notes':['Fixture records pipeline state; actual layout is checked by Chromium.']}})

    def test_draft_gate_prevents_rendering(self):
        self.project['approval_status']='awaiting_user';self.save()
        with self.assertRaisesRegex(ValueError,'awaiting user approval'):
            render(self.path,self.out)
        self.assertFalse(self.out.exists())

    def test_missing_image_stops_before_output(self):
        (self.job/'figure.png').unlink()
        with self.assertRaisesRegex(ValueError,'Asset is missing'):
            render(self.path,self.out)
        self.assertFalse(self.out.exists())

    def test_forged_screenshot_lineage_is_rejected(self):
        self.project['assets'][0].update(role='screenshot',capture_manifest='capture.json')
        save_json(self.job/'capture.json',{'method':'real-browser-screenshot','sha256':'incorrect'})
        self.save()
        with self.assertRaisesRegex(ValueError,'lineage'):
            load(self.path)

    def test_real_ui_mode_rejects_generated_artwork_before_rendering(self):
        self.project.update(visual_policy='real_ui_only',cover={'wide_asset':'figure','square_asset':'figure'})
        self.save()
        with self.assertRaisesRegex(ValueError,'generated artwork'):
            render(self.path,self.out)
        self.assertFalse(self.out.exists())

    def real_ui_fixture(self):
        # Synthetic lineage is confined to a temporary test fixture, never a production screenshot.
        self.project['assets'][0].update(role='screenshot',capture_manifest='capture.json')
        save_json(self.job/'capture.json',{'method':'real-browser-screenshot','sha256':digest(self.job/'figure.png'),
                 'context':'Synthetic unit-test fixture; no real product, capture or account result.'})
        self.project['visual_policy']='real_ui_only'

    def test_real_ui_mode_cannot_fall_back_to_generated_covers(self):
        self.real_ui_fixture();self.save()
        with self.assertRaisesRegex(ValueError,'no generated fallback'):
            render(self.path,self.out)
        self.assertFalse(self.out.exists())

    def test_real_ui_draft_can_be_reviewed_before_cover_selection(self):
        self.real_ui_fixture();self.save()
        draft=load(self.path,'draft')
        self.assertEqual(draft['project']['visual_policy'],'real_ui_only')
        self.assertIn('wechat',draft['drafts'])

    def test_source_covers_preserve_actual_image_and_portable_references(self):
        self.real_ui_fixture()
        self.project['cover']={'wide_asset':'figure','square_asset':'figure'}
        self.save()
        render(self.path,self.out)
        self.assertEqual(digest(self.out/'cover-wide.png'),digest(self.job/'figure.png'))
        self.assertEqual(digest(self.out/'cover-square.png'),digest(self.job/'figure.png'))
        self.assertFalse(read_json(self.out/'cover-wide.meta.json')['generated_artwork'])
        portable=load(self.out/'source/project.json')
        self.assertEqual(portable['project']['visual_policy'],'real_ui_only')
        self.assertEqual(portable['project']['cover']['wide_asset'],'figure')

    def annotated_fixture(self):
        self.real_ui_fixture()
        from annotations import annotate
        annotate(self.job/'figure.png',self.job/'marked.png','figure',[
            {'type':'rect','box':[20,20,90,75],'width':4},
            {'type':'arrow','points':[170,140,95,70],'width':4},
            {'type':'redact','box':[220,20,280,45]}])
        self.project['assets'].append({'id':'marked','path':'marked.png','role':'screenshot',
            'capture_manifest':'marked.capture.json','rights':{'kind':'owned'}})
        self.project['cover']={'wide_asset':'marked','square_asset':'marked'}
        (self.job/'article.md').write_text(self.text.replace('asset:figure','asset:marked'),'utf-8')
        self.save()

    def test_requested_promotion_covers_export_portably_beside_real_body_images(self):
        self.real_ui_fixture()
        self.project['cover']={'design':{'wide_file':'figure.png','square_file':'figure.png','rights':{'kind':'owned'}}}
        self.save()
        render(self.path,self.out)
        self.assertEqual(digest(self.job/'figure.png'),digest(self.out/'cover-wide.png'))
        self.assertEqual(read_json(self.out/'cover-wide.meta.json')['method'],'designed-promotion-cover')
        self.assertFalse(read_json(self.out/'cover-wide.meta.json')['product_screenshot'])
        portable=load(self.out/'source/project.json')
        self.assertEqual(portable['project']['visual_policy'],'real_ui_only')
        import shutil
        shutil.rmtree(self.job)
        result=render(self.out/'source/project.json',self.root/'portable-design')
        self.assertEqual(result['status'],'rendered_pending_review')
        self.assertEqual(digest(self.out/'cover-wide.png'),digest(self.root/'portable-design/cover-wide.png'))

    def test_promotion_cover_permission_does_not_allow_generated_tutorial_images(self):
        self.project.update(visual_policy='real_ui_only',cover={'design':{
            'wide_file':'figure.png','square_file':'figure.png','rights':{'kind':'owned'}}})
        self.save()
        with self.assertRaisesRegex(ValueError,'generated artwork'):
            render(self.path,self.out)
        self.assertFalse(self.out.exists())

    def test_annotations_retain_context_and_export_raw_source(self):
        from PIL import Image
        self.annotated_fixture()
        with Image.open(self.job/'figure.png') as raw, Image.open(self.job/'marked.png') as marked:
            self.assertEqual(raw.size,marked.size)
            self.assertEqual(raw.convert('RGBA').getpixel((500,250)),marked.getpixel((500,250)))
            self.assertNotEqual(raw.convert('RGBA').getpixel((230,30)),marked.getpixel((230,30)))
        render(self.path,self.out)
        portable=load(self.out/'source/project.json')
        self.assertIn('figure',portable['assets'])
        self.assertIn('marked',portable['assets'])
        self.assertTrue(portable['assets']['figure']['absolute_path'].is_relative_to((self.out/'source/originals').resolve()))
        self.assertTrue(portable['assets']['marked']['absolute_path'].is_relative_to((self.out/'assets').resolve()))

    def test_undocumented_pixel_changes_fail_even_with_updated_output_hash(self):
        from PIL import Image
        self.annotated_fixture()
        with Image.open(self.job/'marked.png') as image:
            image.putpixel((500,250),(0,0,0,255))
            image.save(self.job/'marked.png')
        record=read_json(self.job/'marked.capture.json')
        record['sha256']=digest(self.job/'marked.png')
        save_json(self.job/'marked.capture.json',record)
        with self.assertRaisesRegex(ValueError,'beyond the recorded annotations'):
            load(self.path)

    def test_unverified_claim_cannot_support_a_finished_section(self):
        self.project.update(research_mode='provided',research_file='research.json',evidence_map=[
            {'platform':p,'section':'实际检查','claim_ids':['c1']} for p in self.project['platforms']])
        save_json(self.job/'research.json',{'sources':[{'id':'s1','url':'https://example.org','title':'Fixture','checked_at':'2026-10-31'}],
                 'claims':[{'id':'c1','text':'Fixture assertion','source_ids':['s1'],'status':'unverified'}]})
        self.save()
        with self.assertRaisesRegex(ValueError,'Unverified'):
            load(self.path)

    def test_real_render_verify_finalize_and_portable_source(self):
        render(self.path,self.out)
        with self.assertRaises(FileNotFoundError):
            finalize(self.path,self.out)
        result=verify(self.out)
        self.assertTrue(result['passed'])
        self.assertEqual(result['pages_checked'],11)
        self.review()
        final=finalize(self.path,self.out)
        self.assertTrue(Path(final['archive']).is_file())
        self.assertEqual(read_json(self.out/'report.json')['external_state']['publication'],'not_published')
        self.assertIn('print', (self.out/'wechat-body.html').read_text('utf-8'))
        self.assertNotIn('<style', (self.out/'wechat-body.html').read_text('utf-8'))
        # Remove original inputs: the exported source must still render from bundled files.
        import shutil
        shutil.rmtree(self.job)
        rerender=render(self.out/'source/project.json',self.root/'portable-rerender')
        self.assertEqual(rerender['status'],'rendered_pending_review')

    def test_new_wechat_project_delivers_copyable_opening_cover_and_rejects_missing_proof(self):
        from blog import initialize
        from bs4 import BeautifulSoup
        from PIL import Image
        import shutil
        job=self.root/'initialized-job'
        initialize(job,'工具链验收文章','blog,wechat,post')
        path=job/'project.json'
        project=read_json(path)
        project.update(summary='测试描述，不代表真实产品信息。',purpose='临时夹具验证实际交付流程',
                       approval_status='direct',research_mode='none')
        for spec in project['platforms'].values():
            (job/spec['file']).write_text(self.text,'utf-8')
        shutil.copy2(self.job/'figure.png',job/'figure.png')
        Image.new('RGB',(1200,510),'#f47848').save(job/'cover.png')
        project['assets']=[{'id':'figure','path':'figure.png','role':'diagram','rights':{'kind':'owned'}}]
        project['cover']={'design':{'wide_file':'cover.png','square_file':'cover.png','rights':{'kind':'owned'}}}
        project['summary']='甲'*121
        save_json(path,project)
        out=self.root/'initialized-delivery'
        with self.assertRaisesRegex(ValueError,'exceeds 120'):
            render(path,out)
        self.assertFalse(out.exists())
        project['summary']='测试描述，不代表真实产品信息。'
        save_json(path,project)
        render(path,out)
        soup=BeautifulSoup((out/'wechat-body.html').read_text('utf-8'),'html.parser')
        first=soup.select_one('#article').find(True,recursive=False)
        self.assertEqual(first.name,'figure')
        self.assertEqual(digest(out/first.find('img')['src']),digest(job/'cover.png'))
        self.assertIsNone(first.find('figcaption'))
        self.assertEqual(len(soup.select('#article img')),2)
        self.assertEqual(len(BeautifulSoup((out/'blog.html').read_text('utf-8'),'html.parser').select('main #article img')),1)
        self.assertEqual((out/'wechat-description.txt').read_text('utf-8').strip(),project['summary'])
        verify(out)
        verification=read_json(out/'verification.json')
        self.assertTrue(verification['cover_in_body']['passed'])
        self.assertEqual([mode['images'] for mode in verification['clipboard']['modes']],[2,2])
        report=read_json(out/'report.json')
        save_json(job/'review.json',{'status':'reviewed','reviewer':'temporary test fixture',
            'content_hashes':load(path)['hashes'],'findings':[],
            'visual_review':{'render_id':report['render_id'],'screenshots':['qa/top.png'],
                'notes':['Fixture validates workflow; actual article quality requires editorial review.']}})
        for missing,reason in (('cover_in_body','opening-cover'),('clipboard','real clipboard')):
            incomplete=copy.deepcopy(verification)
            incomplete.pop(missing)
            save_json(out/'verification.json',incomplete)
            with self.assertRaisesRegex(ValueError,reason):
                finalize(path,out)
        save_json(out/'verification.json',verification)
        self.assertEqual(finalize(path,out)['status'],'ready_local')
        shutil.rmtree(job)
        portable=self.root/'initialized-portable'
        render(out/'source/project.json',portable)
        self.assertEqual(digest(out/'wechat-body.html'),digest(portable/'wechat-body.html'))

    def test_changed_draft_invalidates_old_delivery(self):
        render(self.path,self.out)
        with (self.job/'article.md').open('a',encoding='utf-8') as f:f.write('\n稿件已经修改。\n')
        with self.assertRaisesRegex(ValueError,'changed after rendering'):
            finalize(self.path,self.out)

    def test_real_clipboard_paste_and_offline_file_keep_two_distinct_images(self):
        from PIL import Image
        from playwright.sync_api import sync_playwright
        import shutil
        Image.new('RGB',(350,170),'#f47848').save(self.job/'second.png')
        self.project['assets'].append({'id':'second','path':'second.png','role':'diagram','rights':{'kind':'owned'}})
        (self.job/'article.md').write_text(self.text+'\n![第二张测试图片](asset:second)\n','utf-8')
        self.save()
        render(self.path,self.out)
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True)
            try:
                result=verify_clipboard(browser,self.out)
                self.assertTrue(result['passed'])
                self.assertEqual([mode['images'] for mode in result['modes']],[2,2])
                # The independent offline file must still work when all packaged image files are gone.
                shutil.rmtree(self.out/'assets')
                page=browser.new_page()
                page.route('**/*',lambda route:route.abort() if route.request.url.startswith(('http:','https:')) else route.continue_())
                page.goto((self.out/'wechat-copy.html').as_uri(),wait_until='load')
                self.assertEqual(page.locator('#article img').count(),2)
                self.assertTrue(page.evaluate("[...document.images].every(img=>img.complete&&img.naturalWidth>0&&img.src.startsWith('data:image/'))"))
            finally:
                browser.close()

    def test_changed_html_invalidates_verification(self):
        render(self.path,self.out)
        with (self.out/'wechat.html').open('a',encoding='utf-8') as f:f.write('<p>tampered</p>')
        with self.assertRaisesRegex(ValueError,'artifact changed'):
            verify(self.out)

    def test_image_must_be_registered_instead_of_a_remote_dependency(self):
        (self.job/'article.md').write_text(self.text.replace('asset:figure','https://example.org/image.png'),'utf-8')
        with self.assertRaisesRegex(ValueError,'Register article images'):
            load(self.path)

    def test_image_mapping_must_match_its_actual_section(self):
        (self.job/'article.md').write_text(self.text+'\n## 另一节\n\n这一节没有图片。\n','utf-8')
        self.project['evidence_map']=[{'platform':'wechat','section':'另一节','asset_ids':['figure']}]
        self.save()
        with self.assertRaisesRegex(ValueError,'outside its mapped section'):
            load(self.path)

    def test_chinese_bold_with_punctuation_preserves_code(self):
        from bs4 import BeautifulSoup
        extra='\n**材料：**官网说明与实际结果分开。\n\n**问题：**看完需要完成什么。\n\n这是**中文（带括号）**强调。\n\n```text\n**代码中的星号不转换：**\n```\n'
        (self.job/'article.md').write_text(self.text+extra,'utf-8')
        render(self.path,self.out)
        soup=BeautifulSoup((self.out/'wechat-body.html').read_text('utf-8'),'html.parser')
        strong=[tag.get_text() for tag in soup.select('strong')]
        self.assertIn('材料：',strong)
        self.assertIn('问题：',strong)
        self.assertIn('中文（带括号）',strong)
        self.assertEqual(soup.select('pre code')[-1].get_text(),'**代码中的星号不转换：**')


class FeedbackAndMetrics(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def test_actual_rewrite_saved_without_becoming_user_approval(self):
        from state import feedback,brief
        before=self.root/'before.md';after=self.root/'after.md'
        before.write_text('这项工具为用户带来新的可能。','utf-8')
        after.write_text('这个工具能把文章导出成 HTML。','utf-8')
        saved=feedback(self.root/'channel',before,after,'替换空泛判断，保留具体动作。')
        self.assertEqual(saved['source'],'editorial')
        self.assertFalse(saved['automatic_profile_update'])
        self.assertEqual(len(brief(self.root/'channel')['feedback']),1)
        with self.assertRaisesRegex(ValueError,'actual textual change'):
            feedback(self.root/'channel',after,after,'No change')

    def test_metrics_compare_matching_platform_and_window_only(self):
        from state import metrics,brief
        record={'article_id':'fixture','platform':'wechat','observed_at':'2026-10-31','window_hours':24,
                'evidence':'Explicit synthetic unit-test data, not user performance','counts':{'views':20}}
        p=self.root/'metrics.json';save_json(p,record)
        self.assertEqual(metrics(self.root/'channel',p)['comparable_observations'],1)
        record.update(article_id='fixture-2',window_hours=48);save_json(p,record)
        self.assertEqual(metrics(self.root/'channel',p)['comparable_observations'],1)
        context=brief(self.root/'channel')
        self.assertEqual(len(context['performance_observations']),2)
        self.assertIn('same platform',context['comparison_rule'])
        record['counts']['views']=-1;save_json(p,record)
        with self.assertRaisesRegex(ValueError,'nonnegative'):
            metrics(self.root/'channel',p)


if __name__=='__main__':
    unittest.main()
