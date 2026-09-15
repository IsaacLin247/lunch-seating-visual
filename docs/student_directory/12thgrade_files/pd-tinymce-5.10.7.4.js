//NS 26735 - needed for puspage
//used to ensure proper relative url prior to absolute url conversion.
//tinyMCE appears to base relative urls on the location of the
//paste plugin htm file instead of document_base_url so urls
//get an extra 3 ../ because of the /tiny_mce/plugins/paste/ directories.
function pasteProcRelUrl(txt) {
    //just get bad rel urls from paste word. They will
    //have 3 or 4 "../" since they are based on pasteword.html location
    //this regex will get urls after href|src that don't have http:\\,https:\\,or mailto:
    //that start with 3 or 4 ../'s.
    //KAM 3/2/12 ns 32921 updated to look for anywhere from 1 to 4 instances to handle issues with copying
    //and pasting a link if FF which was adding 1 case of ../
    var repatt = /(href|src)\s*=\s*([\'"]*(?!http:|https:|mailto:))?((\.\.\/){1,4})(\w*[^\'">]*)/gi;
    var regex = new RegExp(repatt);
    var arrMatches = regex.exec(txt);
    var currUrl, findUrl, curDirs, dirArr;
    while (arrMatches != null && arrMatches != undefined) {
        currDirs = arrMatches[3]; //this will just be ../'s used //to get count
        currUrl = arrMatches[5]; //the url without ../'s

        findUrl = currDirs + currUrl;
        if (String(currUrl).substring(0, 0) != '/') {
            currUrl = '/' + currUrl
        }
        //alert(currDirs + '\n' + currUrl + '\n' + findUrl);
        dirArr = currDirs.match(/\.\.\//gi);
        if (dirArr != null && dirArr != undefined) {
            if (dirArr.length == 4) {
                currUrl = '../' + currUrl;
            }
        }
        findUrl = findUrl.replace(/\//gi, '\\/').replace(/\./gi, '\\.').replace(/\?/gi, '\\?');
        eval('txt=txt.replace(/' + findUrl + '/gi,"' + currUrl + '");');
        //alert(currUrl);
        arrMatches = regex.exec(txt);
    }
    //alert(txt);
    return txt;
}

// HTML Editor
function htmlEditorInit(id, toolbarType, allowFullScreen, initFunction, entityEncoding) {
    var plugins = '';
    var validElements = '';
    var pasteProperties = '';
    var useInlineStyles = false;
    var forcePNewlines = false;
    var forceBrNewlines = true;
    var forcedRootBlock = '';
    var toolBarButtons = '';
    var menu = '';
    var menuBar = '';

    switch (toolbarType) {
        case "full":
            toolBarButtons = 'code | print searchreplace | cut copy paste pastetext | undo redo | table | bold italic underline superscript subscript strikethrough | alignleft aligncenter alignright alignjustify | indent outdent numlist bullist | charmap link unlink anchor';
            useInlineStyles = true;
            break;
        case "limited":
            toolBarButtons = 'code | cut copy paste pastetext | bold italic underline | alignleft aligncenter alignright alignjustify';
            break;
        case "limitedcrystal":
            toolBarButtons = 'code | cut copy paste pastetext | bold italic underline | alignleft aligncenter alignright alignjustify';
            break;
        case "full3line":
            toolBarButtons = 'code | print searchreplace | cut copy paste pastetext | undo redo | table | bold italic underline superscript subscript strikethrough | alignleft aligncenter alignright alignjustify | indent outdent numlist bullist | charmap link unlink anchor';
            break;
        case "merge":
            toolBarButtons = 'code | cut copy paste pastetext | bold italic underline | alignleft aligncenter alignright alignjustify';
            break;
        case "grading":
            toolBarButtons = 'code | bold italic underline | pastetext';
            break;
        case "pushpage":
            toolBarButtons = 'code cut copy paste pastetext | bold italic underline superscript subscript strikethrough table | alignleft aligncenter alignright alignjustify numlist bullist charmap | link unlink anchor formatselect';
            break;
        case "limited2line":
            toolBarButtons = 'code | cut copy paste pasteword pastetext | bold italic underline | alignleft aligncenter alignright alignjustify';
            break;
        case "onlineforms":
            toolBarButtons = 'code | cut copy paste pastetext | bold italic underline | alignleft aligncenter alignright alignjustify';
            break;
        case "fullfont":
            toolBarButtons = 'code print searchreplace | cut copy paste pastetext | undo redo | table | fontsizeselect forecolor| bold italic underline superscript subscript strikethrough | alignleft aligncenter alignright alignjustify | indent outdent numlist bullist | charmap link unlink anchor'
            useInlineStyles = true;
            break;
        case "notification":
            toolBarButtons = 'fontselect fontsizeselect forecolor | cut copy paste pastetext | undo redo | bold italic underline superscript subscript strikethrough | alignleft aligncenter alignright alignjustify | indent outdent numlist bullist | charmap link unlink ';
            break;
    }
    if (allowFullScreen == true) {
        toolBarButtons = 'fullscreen ' + toolBarButtons;
    }

    switch (toolbarType) {
        case "grading":
            plugins = 'fullscreen,paste,tabfocus,code';
            validElements = 'b/strong,i/em,u,br,-span[*]';
            pasteProperties = 'margin,margin-top,margin-bottom,margin-left,margin-right,padding';
            // NS 29774
            // We are replacing all instances of paragraph tags with div tags which are better supported within Crystal
            // and which do not require margin and padding of 0.
            // div/p will replace all P tags with DIV
            // #div[*] will allow all attributes on div tags and will pad empty div tags with &nbsp;
            // don't allow style attribute in div tags here
            validElements += ',div/p,#div[id|align|class|accessKey|dir|lang|tabindex|title]';
            break;
        case "pushpage":
            plugins = 'autoresize,powerpaste,table,tabfocus,code,charmap,anchor,link,lists';
            validElements = '@[id|class|style|title|dir<ltr?rtl|align],'
                + 'a[rel|rev|charset|hreflang|tabindex|accesskey|type|name|href|target|title|class],'
                + 'b/strong,i/em,strike,u,-ol[type|compact],-ul[type|compact],-li,br,'
                + 'img[longdesc|usemap|src|border=0|alt=|title|hspace|vspace|width|height|align],'
                + '-sub,-sup,-blockquote,'
                + '-table[border=0|cellspacing|cellpadding|width|frame|rules|height|align|summary|bgcolor|background|bordercolor],'
                + '-tr[rowspan|width|height|align|valign|bgcolor|background|bordercolor],tbody,thead,tfoot,'
                + '#td[colspan|rowspan|width|height|align|valign|bgcolor|background|bordercolor|scope],'
                + '#th[colspan|rowspan|width|height|align|valign|scope],caption,'
                + '-span,-code,-pre,address,-h1,-h2,-h3,-h4,-h5,-h6,hr[size|noshade],-font[face'
                + '|size|color],dd,dl,dt,cite,abbr,acronym,del[datetime|cite],ins[datetime|cite],'
                + 'map[name],area[shape|coords|href|alt|target],bdo,'
                + 'button,col[align|char|charoff|span|valign|width],colgroup[align|char|charoff|span|valign|width],'
                + 'kbd,label[for],legend,optgroup[label|disabled],option[disabled|label|selected|value],'
                + 'q[cite],samp,select[disabled|multiple|name|size],small';
            pasteProperties = 'font-size,color,margin,margin-top,margin-bottom,margin-left,margin-right,padding';
            // Setting these for pushpage fixes an issue with alignment not working in certain browsers
            // In the future, may need to set these by default to fix all areas of the system
            useInlineStyles = true;
            forcePNewlines = true;
            forceBrNewlines = false;
            forcedRootBlock = 'div';
            // NS 29774
            // We are replacing all instances of paragraph tags with div tags which are better supported within Crystal
            // and which do not require margin and padding of 0.
            // div/p will replace all P tags with DIV
            // #div[*] will allow all attributes on div tags and will pad empty div tags with &nbsp;
            validElements += ',div/p[*],#div[*]';
            break;
        case "limitedcrystal":
            /*NS 29774
            We are replacing all instances of paragraph tags with div tags which are better supported within Crystal
            and which do not require margin and padding of 0.
            div/p will replace all P tags with DIV
            #div[*] will allow all attributes on div tags and will pad empty div tags with&nbsp;*/
            validElements = 'b/strong,i/em,u,br,-span[*]';
            pasteProperties = 'margin,margin-top,margin-bottom,margin-left,margin-right,padding';
            //validElements += ',div/p,#div[id|align|class|accessKey|dir|lang|tabindex|title|style<text-align: left;?text-align: center;?text-align: right;?text-align: justify;text-align:left;?text-align:center;?text-align:right;?text-align:justify;]';
            validElements += ',div/p,#div[id|class|accessKey|dir|lang|tabindex|title|style]';
            plugins = 'code';
            break;
        case "onlineforms":
            plugins = 'paste,tabfocus,autoresize,code';
            validElements = '*[*],b/strong,i/em,script[src|type|id|class],-span[*],-font[*]';
            pasteProperties = 'font-size,color,margin,margin-top,margin-bottom,margin-left,margin-right,padding';
            // NS 29774
            // We are replacing all instances of paragraph tags with div tags which are better supported within Crystal
            // and which do not require margin and padding of 0.
            // div/p will replace all P tags with DIV
            // #div[*] will allow all attributes on div tags and will pad empty div tags with &nbsp;
            validElements += ',div/p,#div[*]';
            break;
        default:
            plugins = 'media,fullscreen,powerpaste,print,searchreplace,table,tabfocus,code,charmap,anchor,link,link,lists';
            validElements = '*[*],b/strong,i/em,script[src|type|id|class],-span[*],-font[*]';
            pasteProperties = 'font-size,color,margin,margin-top,margin-bottom,margin-left,margin-right,padding';
            // NS 29774
            // We are replacing all instances of paragraph tags with div tags which are better supported within Crystal
            // and which do not require margin and padding of 0.
            // div/p will replace all P tags with DIV
            // #div[*] will allow all attributes on div tags and will pad empty div tags with &nbsp;
            validElements += ',div/p[*],#div[*]';
            break;
    }

    tinyMCE.init({
        mode: 'exact',
        elements: id,
        language: "en",
        plugins: plugins,
        button_tile_map: true,
        forced_root_block: forcedRootBlock,
        force_p_newlines: forcePNewlines,
        force_br_newlines: forceBrNewlines,
        remove_redundant_brs: false,
        valid_elements: validElements,
        /* Had to use valid_styles for the limited editor because all other ways to limit the style attribute caused bugs in Safari only */
        valid_styles: toolbarType == "limitedcrystal" ? { '*': 'text-align' } : '',
        invalid_elements: "st1:*",
        convert_fonts_to_spans: false,
        inline_styles: useInlineStyles,
        paste_retain_style_properties: pasteProperties,
        paste_auto_cleanup_on_paste: true,
        content_style: ".mceContentBody {font-size:15px;}",
        paste_preprocess: function (pl, o) {
            o.content = pasteProcRelUrl(o.content);
        },
        paste_postprocess: function (pl, o) {
            var html = o.node.innerHTML;
            html = html.replace(/\<div id="_mcePaste[^\>]*\>/gi, '<div>');
            o.node.innerHTML = html;
        },
        cleanup_callback: function (type, value) {
            var val = value;
            if ((type == 'get_from_editor') || (type == 'insert_to_editor')) {
                val = val.replace(/\<\/\*span-[^\>]*\>/gi, '');
                // Cleanup Browser Highlighter AddOn Junk
                val = val.replace(/\<div[^\>]*refHTML[^\>]*\>[^\>]*\<\/div\>/gi, '');
                val = val.replace(/\<input[^\>]*gwProxy[^\>]*\/\>/gi, '');
                val = val.replace(/\<input[^\>]*jsProxy[^\>]*\/\>/gi, '');

                //NS 28367 - Cleanup weird span-style-span tag that sometimes gets added
                //repeatedly when pasting html
                val = val.replace(/\<[^\>]*span-style-span[^\>]*\>.*?\<\/[^\>]*span-style-span[^\>]*\>/gi, '');

                // NS 33530 - Cleanup invalid width="auto"/height="auto" for IE
                val = val.replace(/width=\"auto\"/gi, '');
                val = val.replace(/height=\"auto\"/gi, '');

                // Remove word junk
                val = val.replace(/\<xml>(.+?)<\/xml\>/gi, '');
                val = val.replace(/\<style>(.+?)<\/style\>/gi, '');
                val = val.replace(/\<meta[^\>]*\/\>/gi, '');
                val = val.replace(/\<w:[^\>]*\/\>[\\n]*/gi, '');

                val = val.replace(/\<script[^\>]*rtdock\.com[^\>]*\>/gi, '');

                if (toolbarType === 'grading') { // JW OR-58 and OR-61. Unicode characters getting into DB through non Podium comments. then erroring during review when parsed in XML
                    val = val.replace(/[\0-\x1F\x7F-\x9F\xAD\u0378\u0379\u037F-\u0383\u038B\u038D\u03A2\u0528-\u0530\u0557\u0558\u0560\u0588\u058B-\u058E\u0590\u05C8-\u05CF\u05EB-\u05EF\u05F5-\u0605\u061C\u061D\u06DD\u070E\u070F\u074B\u074C\u07B2-\u07BF\u07FB-\u07FF\u082E\u082F\u083F\u085C\u085D\u085F-\u089F\u08A1\u08AD-\u08E3\u08FF\u0978\u0980\u0984\u098D\u098E\u0991\u0992\u09A9\u09B1\u09B3-\u09B5\u09BA\u09BB\u09C5\u09C6\u09C9\u09CA\u09CF-\u09D6\u09D8-\u09DB\u09DE\u09E4\u09E5\u09FC-\u0A00\u0A04\u0A0B-\u0A0E\u0A11\u0A12\u0A29\u0A31\u0A34\u0A37\u0A3A\u0A3B\u0A3D\u0A43-\u0A46\u0A49\u0A4A\u0A4E-\u0A50\u0A52-\u0A58\u0A5D\u0A5F-\u0A65\u0A76-\u0A80\u0A84\u0A8E\u0A92\u0AA9\u0AB1\u0AB4\u0ABA\u0ABB\u0AC6\u0ACA\u0ACE\u0ACF\u0AD1-\u0ADF\u0AE4\u0AE5\u0AF2-\u0B00\u0B04\u0B0D\u0B0E\u0B11\u0B12\u0B29\u0B31\u0B34\u0B3A\u0B3B\u0B45\u0B46\u0B49\u0B4A\u0B4E-\u0B55\u0B58-\u0B5B\u0B5E\u0B64\u0B65\u0B78-\u0B81\u0B84\u0B8B-\u0B8D\u0B91\u0B96-\u0B98\u0B9B\u0B9D\u0BA0-\u0BA2\u0BA5-\u0BA7\u0BAB-\u0BAD\u0BBA-\u0BBD\u0BC3-\u0BC5\u0BC9\u0BCE\u0BCF\u0BD1-\u0BD6\u0BD8-\u0BE5\u0BFB-\u0C00\u0C04\u0C0D\u0C11\u0C29\u0C34\u0C3A-\u0C3C\u0C45\u0C49\u0C4E-\u0C54\u0C57\u0C5A-\u0C5F\u0C64\u0C65\u0C70-\u0C77\u0C80\u0C81\u0C84\u0C8D\u0C91\u0CA9\u0CB4\u0CBA\u0CBB\u0CC5\u0CC9\u0CCE-\u0CD4\u0CD7-\u0CDD\u0CDF\u0CE4\u0CE5\u0CF0\u0CF3-\u0D01\u0D04\u0D0D\u0D11\u0D3B\u0D3C\u0D45\u0D49\u0D4F-\u0D56\u0D58-\u0D5F\u0D64\u0D65\u0D76-\u0D78\u0D80\u0D81\u0D84\u0D97-\u0D99\u0DB2\u0DBC\u0DBE\u0DBF\u0DC7-\u0DC9\u0DCB-\u0DCE\u0DD5\u0DD7\u0DE0-\u0DF1\u0DF5-\u0E00\u0E3B-\u0E3E\u0E5C-\u0E80\u0E83\u0E85\u0E86\u0E89\u0E8B\u0E8C\u0E8E-\u0E93\u0E98\u0EA0\u0EA4\u0EA6\u0EA8\u0EA9\u0EAC\u0EBA\u0EBE\u0EBF\u0EC5\u0EC7\u0ECE\u0ECF\u0EDA\u0EDB\u0EE0-\u0EFF\u0F48\u0F6D-\u0F70\u0F98\u0FBD\u0FCD\u0FDB-\u0FFF\u10C6\u10C8-\u10CC\u10CE\u10CF\u1249\u124E\u124F\u1257\u1259\u125E\u125F\u1289\u128E\u128F\u12B1\u12B6\u12B7\u12BF\u12C1\u12C6\u12C7\u12D7\u1311\u1316\u1317\u135B\u135C\u137D-\u137F\u139A-\u139F\u13F5-\u13FF\u169D-\u169F\u16F1-\u16FF\u170D\u1715-\u171F\u1737-\u173F\u1754-\u175F\u176D\u1771\u1774-\u177F\u17DE\u17DF\u17EA-\u17EF\u17FA-\u17FF\u180F\u181A-\u181F\u1878-\u187F\u18AB-\u18AF\u18F6-\u18FF\u191D-\u191F\u192C-\u192F\u193C-\u193F\u1941-\u1943\u196E\u196F\u1975-\u197F\u19AC-\u19AF\u19CA-\u19CF\u19DB-\u19DD\u1A1C\u1A1D\u1A5F\u1A7D\u1A7E\u1A8A-\u1A8F\u1A9A-\u1A9F\u1AAE-\u1AFF\u1B4C-\u1B4F\u1B7D-\u1B7F\u1BF4-\u1BFB\u1C38-\u1C3A\u1C4A-\u1C4C\u1C80-\u1CBF\u1CC8-\u1CCF\u1CF7-\u1CFF\u1DE7-\u1DFB\u1F16\u1F17\u1F1E\u1F1F\u1F46\u1F47\u1F4E\u1F4F\u1F58\u1F5A\u1F5C\u1F5E\u1F7E\u1F7F\u1FB5\u1FC5\u1FD4\u1FD5\u1FDC\u1FF0\u1FF1\u1FF5\u1FFF\u200B-\u200F\u202A-\u202E\u2060-\u206F\u2072\u2073\u208F\u209D-\u209F\u20BB-\u20CF\u20F1-\u20FF\u218A-\u218F\u23F4-\u23FF\u2427-\u243F\u244B-\u245F\u2700\u2B4D-\u2B4F\u2B5A-\u2BFF\u2C2F\u2C5F\u2CF4-\u2CF8\u2D26\u2D28-\u2D2C\u2D2E\u2D2F\u2D68-\u2D6E\u2D71-\u2D7E\u2D97-\u2D9F\u2DA7\u2DAF\u2DB7\u2DBF\u2DC7\u2DCF\u2DD7\u2DDF\u2E3C-\u2E7F\u2E9A\u2EF4-\u2EFF\u2FD6-\u2FEF\u2FFC-\u2FFF\u3040\u3097\u3098\u3100-\u3104\u312E-\u3130\u318F\u31BB-\u31BF\u31E4-\u31EF\u321F\u32FF\u4DB6-\u4DBF\u9FCD-\u9FFF\uA48D-\uA48F\uA4C7-\uA4CF\uA62C-\uA63F\uA698-\uA69E\uA6F8-\uA6FF\uA78F\uA794-\uA79F\uA7AB-\uA7F7\uA82C-\uA82F\uA83A-\uA83F\uA878-\uA87F\uA8C5-\uA8CD\uA8DA-\uA8DF\uA8FC-\uA8FF\uA954-\uA95E\uA97D-\uA97F\uA9CE\uA9DA-\uA9DD\uA9E0-\uA9FF\uAA37-\uAA3F\uAA4E\uAA4F\uAA5A\uAA5B\uAA7C-\uAA7F\uAAC3-\uAADA\uAAF7-\uAB00\uAB07\uAB08\uAB0F\uAB10\uAB17-\uAB1F\uAB27\uAB2F-\uABBF\uABEE\uABEF\uABFA-\uABFF\uD7A4-\uD7AF\uD7C7-\uD7CA\uD7FC-\uF8FF\uFA6E\uFA6F\uFADA-\uFAFF\uFB07-\uFB12\uFB18-\uFB1C\uFB37\uFB3D\uFB3F\uFB42\uFB45\uFBC2-\uFBD2\uFD40-\uFD4F\uFD90\uFD91\uFDC8-\uFDEF\uFDFE\uFDFF\uFE1A-\uFE1F\uFE27-\uFE2F\uFE53\uFE67\uFE6C-\uFE6F\uFE75\uFEFD-\uFF00\uFFBF-\uFFC1\uFFC8\uFFC9\uFFD0\uFFD1\uFFD8\uFFD9\uFFDD-\uFFDF\uFFE7\uFFEF-\uFFFB\uFFFE\uFFFF]/g, '');
                }
            }
            return val;
        },
        save_callback: function (element_id, html, body) {
            // regular expression to make sure html is not just an empty div region
            html = html.replace(/^\<div\>\&nbsp\;\<\/div\>$/gi, '');
            return html;
        },
        //NS 28096 - This is an overwrite of the FormatBlock
        //function in Podium\tinymce\tiny_mce_src.js line 10241
        //We're rewriting it to apply block formatting to the
        //selected text instead of the current block element node
        //as clients we're getting confused when entire blocks were
        //getting formatting 
        //acoording to tinyMCE docs this is the old way to override command, but addCommand
        //doesn't appear to work in chrome/safari.
        execcommand_callback: function (editor_id, elm, command, user_interface, value) {
            if (command == 'mceRepaint') {
                // BTS NS 33260
                // Fix for Firefox 11 when exiting fullscreen mode
                htmlEditorFixFF11();
            }

            if (editor_id != 'pp_edittext') { return false; }
            switch (command) {
                case "FormatBlock":
                    var ed = tinyMCE.getInstanceById(editor_id), val = value;
                    var s = ed.selection, dom = ed.dom, bl, nb, b;
                    var isIE = tinymce.isIE, isGecko = tinymce.isGecko;
                    var content = s.getContent(), rBlock = ed.settings.forced_root_block;
                    var sNode = s.getNode();
                    //move this up heare to prevent error in IE when val has no value
                    val = ed.settings.forced_root_block ? (val || 'div') : val;
                    function newBlock(formats, n, val) {
                        var ret = false;
                        //alert('in newBlock:\n' + n.nodeName.toLowerCase() + '\n' + val);
                        //alert(String(formats.indexOf(n.nodeName.toLowerCase()) < 0) + ' || ' + String((n.nodeName.toLowerCase() == 'p' && val.toLowerCase() != 'p')));
                        if (formats.indexOf(n.nodeName.toLowerCase()) < 0 || (n.nodeName.toLowerCase() == 'div' && val.toLowerCase() != 'div')) {
                            ret = true;
                        }
                        //alert(ret);
                        return ret;
                    }
                    //s.getRng(true);
                    //if there's selected content and the content is not in one of the set
                    //block format nodes or node is p and val is not p(we can have h1/h2 nodes
                    //in a p tag) then add a rootblock(div in pp) around it to make new block
                    if (content.length > 0 && newBlock(ed.settings.theme_advanced_blockformats, sNode, val)) {
                        //alert('**\n'+sNode.nodeName.toLowerCase);
                        //selection.SetNode doesn't work in firefox for some reason so use this instead
                        s.setContent('<' + rBlock + ' id="__tmp_' + rBlock + '">' + content + '</' + rBlock + '>');
                        s.select(ed.getDoc().getElementById('__tmp_' + rBlock), 1);
                        //s.setNode(ed.getDoc().getElementById('__tmp_' + rBlock));
                        dom.setAttrib('__tmp_' + rBlock, 'id', null);
                        //alert(rBlock + '||\n ' + content + '\n\n\n' + s.getContent()); //Node().innerHTML
                    }

                    function isBlock(n) {
                        return /^(P|DIV|H[1-6]|ADDRESS|BLOCKQUOTE|PRE)$/.test(n.nodeName);
                    };

                    bl = dom.getParent(s.getNode(), function (n) {
                        return isBlock(n);
                    });

                    // IE has an issue where it removes the parent div if you change format on the paragrah in <div><p>Content</p></div>
                    // FF and Opera doesn't change parent DIV elements if you switch format
                    if (bl) {
                        if ((isIE && isBlock(bl.parentNode)) || bl.nodeName == 'DIV') {
                            // Rename block element
                            nb = ed.dom.create(val);
                            tinymce.each(dom.getAttribs(bl), function (v) {
                                dom.setAttrib(nb, v.nodeName, dom.getAttrib(bl, v.nodeName));
                            });

                            b = s.getBookmark();
                            //alert('bef replace\n'+nb+'\n\n'+bl.innerHTML);
                            dom.replace(nb, bl, 1);
                            //alert('aft replace');
                            s.moveToBookmark(b);
                            ed.nodeChanged();
                            return true;
                        }
                    }

                    /*if (val.indexOf('<') == -1)
                    val = '<' + val + '>';

                    if (tinymce.isGecko)
                    val = val.replace(/<(div|blockquote|code|dt|dd|dl|samp)>/gi, '$1');*/

                    ed.getDoc().execCommand('FormatBlock', false, val);
                //return true;
            }
            return false;
        },

        //NS 26735 - make all relative urls absolute
        //Pushpage content can't have relative urls.
        convert_urls: true,
        relative_urls: false,
        remove_script_host: false,
        document_base_url: location.protocol + '//' + location.host + '/podium/',

        // Fixed an issue where the dialog.css file was not resolving correctly in p3
        // Not sure if there is a better way to handle this without hardcoding.
        popup_css: '//libs-e1.myschoolapp.com/tinymce/3.5.8.5/tiny_mce/themes/advanced/skins/default/dialog.css',
        init_instance_callback: initFunction,
        browser_spellcheck: true,
        setup: function (ed) {
            ed.on('event', function (args) {
                htmlEditorStoreBookmark(ed);
            });

            ed.on('PostProcess', function (e) {
                e.content = e.content.replace(/\s*ncwce="true"/gi, '');
            });

            if (id == 'pp_edittext') {

                ed.on('init', function (args) {
                    // BTS 09/20/2010 - NS27890 - scrollbars causing an issue in firefox
                    $('#pp_edittext_ifr').attr('scrolling', 'no');
                    ed.focus();
                });
                ed.on('mousedown', function (args) { ppHideImageMenu(); });
                ed.on('mouseup', function (args) { ppInitImageEdit(); });
            }
        },
        class_filter: function (cls, rule) { return false; },
        urlconverter_callback: function (url, node, on_save) {
            // Fix for IE replacing anchor tags with full url.  Used for detail pages and backlinks in pushpage2010
            if ((url.indexOf('/podium/default.aspx') >= 0) && ((url.indexOf('#dp:') >= 0) || (url.indexOf('#bl') >= 0))) {
                return '#' + url.split('#')[1];
            } else {
                return url;
            }
        },
        entity_encoding: entityEncoding,
        formats: {
            underline: { inline: 'u', exact: true }
        },
        // New properties for v5 among other things a single toolbar replaces the multiple rows
        // We also have the option of using menus instead of or to duplicate toolbar functions
        branding: false, //turns off Powered by tiny message
        toolbar: toolBarButtons,
        toolbar_mode: 'sliding',
        menubar: menuBar,
        menu: menu,
        contextmenu: false,
        // They added this property and defaulted it to false, in the past you could just paste
        // and image in, they seem to discourage flipping this on, but we have been asked to 
        // restore the previous functionality
        paste_data_images: true,
        powerpaste_allow_local_image: true,

        // enable resizing this requires status bar to be enabled, hide element path
        // so that the only thing in the status bar is the resize handle
        resize: 'both',
        statusbar: true,
        elementpath: false
    });
}

// Bootstrap modal grabs this event, use stopImmediatePropagation to allow normal event focus in tinyMCE modals
$(document).on('focusin', function (e) {
    var $target = $(e.target);
    if ($target.closest(".tox-tinymce-aux, .moxman-window, .tam-assetmanager-root").length) {
        e.stopImmediatePropagation();
    }
});

// Bootstrap modal grabs this event, use stopImmediatePropagation to allow normal mousedown processing in tinyMCE modals
$(document).on('mousedown', function (e) {
    if ($(e.target).closest(".tox-tinymce-aux, .moxman-window, .tam-assetmanager-root").length) {
        e.stopImmediatePropagation();
    }
});

function htmlEditorFixFF11() {
    // Causes a resize event which fixes an issue in Firefox 11
    if ($.browser.mozilla && $.browser.version.indexOf("11") == 0) {
        setTimeout(function () { $('.mceIframeContainer iframe').each(function (i) { $(this).height($(this).height() + 1); }); }, 1000);
    }
}

function htmlEditorSave(id) {
    var editor = tinyMCE.get(id);
    if (editor) {
        editor.save();
        fInitFormChange();
    }
}

function htmlEditorRemove(id) {
    var editor = tinyMCE.get(id);
    editor.remove();
}

function htmlEditorInsertContent(id, content) {
    var editor = tinyMCE.get(id);
    htmlEditorReStoreBookmark(editor);
    editor.execCommand('mceInsertContent', false, content);
    htmlEditorStoreBookmark(editor);
}

var htmlEditorBookmark = false;
function htmlEditorStoreBookmark(editor) {
    htmlEditorBookmark = htmlEditorBookmark = editor.selection.getBookmark(2, true);
}

function htmlEditorReStoreBookmark(editor) {
    editor.selection.moveToBookmark(htmlEditorBookmark);
}