/*!
 * PiBox Javascript
 * Author: MCHilli
*/

var vers = "2.2.0"

// FUNCTIONS //
function declareGlobVars() {
    window.globalData = {};
    window.dictionary = {};
    window.themeProps = [
        '--primary-color',
        '--secondary-color',
        '--hover-color'
    ];
    window.globalCurrent = {};
    window.backupCurrent = {};
    window.progressInterval = undefined;
    window.volumeButtonHold = undefined;
    window.volumeButtonStep = undefined;
    window.directoryContent = [];
    window.directorySearch = new List('content', {
        valueNames: ['name'],
        listClass: 'directory'
    });
    window.globalTracklist = [];
    window.backupTracklist = [];
    window.tracklistSearch = new List('tracklist', {
        valueNames: ['index', 'title'],
        listClass: 'list'
    });
    window.changedConfig = false;

    window.logCSSSuccess = 'color: lightgreen; font-weight:bold;';
    window.logCSSInfo = 'color: dodgerblue; font-weight:bold;';
    window.logCSSError = 'color: red; font-weight:bold;';

    window.root = $(':root');
    window.metaTheme = $('meta[name="theme-color"]');
    window.loadingDOM = $('#loading');
    window.logoDOM = $('#logo');

    window.topbarDOM = $('#topbar');
    window.positionDOM = topbarDOM.children('.position');
    window.progressDOM = topbarDOM.children('.progress');
    window.durationDOM = topbarDOM.children('.duration');
    window.stateIconDOM = topbarDOM.find('.icon i');
    window.stateInfoDOM = topbarDOM.children('.info');
    window.stateIndexDOM = stateInfoDOM.children('.index');
    window.stateTitleDOM = stateInfoDOM.children('.title');
    window.stateTitleTextDOM = stateTitleDOM.children('div');

    window.sidebarDOM = $('#sidebar');
    window.stateButtonDOM = sidebarDOM.children('.button.play');
    window.stateButtonIconDOM = stateButtonDOM.children('i');
    window.modeButtonDOM = sidebarDOM.children('.button.mode');
    window.modeButtonIconDOM = modeButtonDOM.children('i');
    window.tracklistBadgeDOM = sidebarDOM.find('.button.tracklist .badge');

    window.contentDOM = $('#content');
    window.pathDOM = contentDOM.children('.path');
    window.directoryDOM = contentDOM.children('.directory');
    window.searchDOM = $('#search');
    window.searchBadgeDOM = searchDOM.children('.badge');
    window.searchIconDOM = searchDOM.children('.icon');

    window.tracklistDOM = $('#tracklist');
    window.tracklistHeaderDOM  = tracklistDOM.children('.header');
    window.tracklistHeaderSearchDOM  = tracklistHeaderDOM.children('.button.search');
    window.tracklistListDOM = tracklistDOM.children('.list');
    window.tracklistListHeaderDOM = tracklistDOM.children('.list-header');
    window.tracklistListHeaderCenterDOM = tracklistListHeaderDOM.find('.center');
    window.tracklistListHeaderCountDOM = tracklistListHeaderDOM.find('.count');
    window.tracklistListHeaderDurationDOM = tracklistListHeaderDOM.children('.duration');

    window.configDOM = $('#config');
    window.subWindowsDOM = $('.subwindow');

    window.versions = {
        html: $('meta[name=version]').attr('content'),
        css: root.css('--version').replace(/\"/g,"").trim(),
        js: vers
    };
}
function getTranslation(property) {
    // return translated string from dictionary
    try {
        let translation = dictionary;
        let string;
        let values = undefined;
        if (typeof property === 'string') {
            string = property;
        } else if (property instanceof Array) {
            string = property[0];
            values = property.slice(1);
        }
        string.split('.').forEach(key => {
            translation = translation[key];
        })
        // replace placeholder with values if given
        if (values) {
            for (let v of values) {
                translation = translation.replace(/%s/, v);
            }
        }
        return translation
    } catch (e) {
        return 'undefined'
    };
}
function translateDOM() {
    // translate all DOM elements
    let elements = document.querySelectorAll('[data-title], [data-content]');
    elements.forEach((element) => {
        let data = element.dataset;
        if ("title" in data) {
            element.title = getTranslation(data.title);
        }
        if ("content" in data) {
            element.innerHTML = getTranslation(data.content);
        }
    });
}
function initTranslation(lang, async=true) {
    // initialize translation
    return $.ajax({
        dataType: "json",
        url: `/lang/${lang}.json`,
        async: async,
        success: (data) => {
            // write transaltion in dictionary
            dictionary = data;
        },
        error: () => {
            console.log('%c>>> Error while loading translation file', logCSSError);
            console.log('%c>>> loading default translation instead', logCSSInfo);
            // load synced to prevent startup without strings
            initTranslation('en', false);
        }
    });
}
function initWebsocket() {
    // initialize websocket
    window.websocket = new WebSocket("ws://"+globalData.own_ip+":"+globalData.websocket_port+"/");
    websocket.onopen = function(){
        // websocket open
        console.log("%c>>> Websocket Server connected", logCSSSuccess);
        createToast({
            message: getTranslation('toast.connect')
        });
        loadingDOM.removeClass('fullscreen');
        let url = getStorage("url");
        if (!url) {
            url = globalData.base_path;
        }
        sendCmd("system_get_directory", url);
    };
    websocket.onmessage = function(e){
        // receive message from websocket
        var data = JSON.parse(e.data);
        // console.log(data);
        switch(data.cmd) {
            case "config":
                updateData(data.data)
                break;
            case "directory":
                updateDirectory(data.data);
                break;
            case "tracklist":
                updateTracklist(data.data);
                break;
            case "current":
                updateCurrent(data.data);
                break;
            case "volume":
                updateVolume(data.data);
                break;
            case "mode":
                updateModebutton(data.data);
                break;
            case "toast":
                createToast({
                    message: getTranslation(data.data)
                });
                break;
            default:
                console.log('unkown command');
        }
    };
    websocket.onclose = function(){
        // websocket close
        console.log("%c>>> Websocket Server disconnected", logCSSError);
        createToast({
            message: getTranslation('toast.disconnect')
        });
        document.title = getTranslation('misc.disconnect');
        showLoading();
        setTimeout(function() {
            if (changedConfig) {
                location.reload();
            } else {
                initWebsocket();
            }
        }, 5000);
    };
}
function updateData(data) {
    // write received configuration to global data
    $.extend(globalData, data);
    document.title = globalData.pibox_name;
    updateTheme();
    readConfig();
}
function sendCmd(cmd, data = "") {
    // send message to websocket
    let payload = JSON.stringify({
        'cmd':cmd,
        'data':data
    });
    websocket.send(payload);
}
function getStorage(name) {
    // read local storage
    return window.localStorage.getItem(name);
}
function setStorage(name, value) {
    // write local storage
    window.localStorage.setItem(name, value);
}
function delStorage(name) {
    // delete local storage
    window.localStorage.removeItem(name);
}
function setTheme(theme) {
    // set the theme colors
    let colors = [
        '#000000',
        '#FFFFFF',
        '#808080'
    ];
    for (var i = 0; i < theme.length; i++) {
        colors[i] = theme[i]
    }
    root.css(themeProps[0], colors[0])
        .css(themeProps[1], colors[1])
        .css(themeProps[2], colors[2]);
    metaTheme.attr('content', colors[0]);
}
function updateTheme() {
    // update theme to global or local if cookie exist
    let theme = getStorage("theme");
    if (theme) {
        setTheme(JSON.parse(theme));
    } else if (globalData) {
        setTheme([
            globalData.theme_primary,
            globalData.theme_secondary,
            globalData.theme_hover
        ])
    }
}
function checkMobile() {
    // return true if the device is a mobile device
    if ( navigator.userAgent.match(/Android/i)
     || navigator.userAgent.match(/webOS/i)
     || navigator.userAgent.match(/iPhone/i)
     || navigator.userAgent.match(/iPad/i)
     || navigator.userAgent.match(/iPod/i)
     || navigator.userAgent.match(/BlackBerry/i)
     || navigator.userAgent.match(/Windows Phone/i)) {
        return true;
    } else {
        return false;
    }
}
function getDuration(ms) {
    // convert ms in readable format
    if (ms <= '0') {
        return "00:00";
    }
    let sec = Math.floor(ms / 1000);
    let min = Math.floor(sec / 60);
    let hr = Math.floor(min / 60);
    sec = (sec % 60 < 10 ? "0" + sec % 60 : sec % 60);
    min = (min % 60 < 10 ? "0" + min % 60 : min % 60);
    hr = (hr % 60 < 10 ? "0" + hr % 60 : hr % 60);
    if (hr == "00") {
        return `${min}:${sec}`;
    } else {
        return `${hr}:${min}:${sec}`;
    }
}
function showLoading(fullscreen=true) {
    // show loading overlay
    if (fullscreen) {
        loadingDOM.removeAttr('class')
                  .addClass('fullscreen');
    } else {
        loadingDOM.removeAttr('class');
    }
}
function createLoading(settings) {
    // show a loading overlay
    /*
    settings {
        parent:     string      # parent object to append the loading overlay
    }
    */
    let props = {
        parent: '#layout',
        DOM: undefined,
        initialize: function() {
            for (let prop in settings) {
                props[prop] = settings[prop];
            }
            props.DOM = $('<div id="loading"></div>');
            props.DOM.addClass('invisible');
            let loader = $('<div class="loader"></div>');
            props.DOM.append(loader);
            return props;
        },
        normalize: function() {
            props.DOM.removeClass('fullscreen');
            return props;
        },
        fullscreen: function() {
            props.DOM.addClass('fullscreen');
            return props;
        },
        append: function() {
            $(props.parent).append(props.DOM);
            setTimeout(function() {
                props.DOM.removeClass('invisible');
            }, 100);
            return props;
        },
        detach: function() {
            props.DOM.addClass('invisible');
            setTimeout(function() {
                props.DOM.detach()
            }, 500);
            return props;
        }
    }
    return props.initialize();
}
function hideSubbars() {
    // hide the opened subbars
    let subbarButton = sidebarDOM.children('.button.subbar');
    let subbarDOM = sidebarDOM.find('.button .subbar');
    let subbarOverlay = sidebarDOM.children('.subbar-overlay');
    subbarButton.addClass('hover');
    subbarDOM.hide();
    subbarOverlay.remove();
}
function createDialog(settings) {
    // generates a dialog based on the given settings
    /*
    settings {
        parent:         string      # parent object to append the dialog
        class:          string      # additional class for the dialog
        width:          int         # specify a min-width for the dialog
        alert:          boolean     # if the dialog is an alert, no cancel
        prompt:         boolean     # if the dialog a prompt, with input
        notification:   boolean     # if the dialog is a notification, autoclose 1s
        timeout:        int         # time in ms for autoclose the notification
        placeholder:    string      # placeholder value for prompt dialog
        title:          string      # title of the dialog
        content:        string      # content of the dialog
        onload:         function    # fired after dialog appended but before visible
        onunload:       function    # fired before dialog detached from parent
        onok:           function    # fired on ok button
        oncancel:       function    # fired on cancel button
        labelok:        string      # label for the ok button
        labelcancel:    string      # label for the cancel button
        buttons:        array of objects    # label:    string      # label of the button
                                            # function: function    # function of the button
    }
    */
    let props = {
        parent: '#layout',
        class: undefined,
        DOM: {},
        width: undefined,
        alert: false,
        prompt: false,
        notification: false,
        timeout: 1000,
        title: 'PiBox',
        content: 'undefined',
        onload: function() {
            return true;
        },
        onunload: function() {
            return true;
        },
        onok: function() {
            return true;
        },
        oncancel: function() {
            return true;
        },
        labelok: getTranslation('dialog.button.ok'),
        labelcancel: getTranslation('dialog.button.cancel'),
        buttons: [],
        cleanup: function() {
            props.onunload({data: {dialog: props}});
            props.DOM.dialog.addClass('invisible');
            props.DOM.dialog.off('click');
            setTimeout(function() {
                props.DOM.dialog.detach();
            }, 500);
        }
    }
    for (let prop in settings) {
        if (prop == "buttons") {
            for (let i = 0; i < settings[prop].length; i++) {
                props.buttons.push(settings[prop][i]);
            }
        } else {
            props[prop] = settings[prop]
        }
    }
    if (!props.notification) {
        props.buttons.unshift({
            label: props.labelok,
            function: props.onok
        });
    }
    if (!(props.alert || props.notification)) {
        props.buttons.push({
            label: props.labelcancel,
            function: props.oncancel
        });
    }
    props.DOM.dialog = $('<div id="dialog"></div>');
    props.DOM.dialog.addClass(props.class);
    let dialog = $('<div class="dialog"></div>');
    if (props.width) {
        dialog.css('min-width', props.width);
    }
    props.DOM.header = $('<div class="header">' + props.title + '</div>');
    props.DOM.content = $('<div class="content">' + props.content + '</div>');
    if (props.prompt) {
        props.value = $('<input type="text" class="value">');
        props.value.attr('placeholder', props.placeholder);
        props.DOM.content.append(props.value);
        props.DOM.content.on('keyup', function(e){
            switch (e.key) {
                case 'Enter':
                    props.onok({data: {dialog: props}});
                    props.cleanup();
                    break
                case 'Escape':
                    props.oncancel({data: {dialog: props}});
                    props.cleanup();
                    break
                default:
                    return;
            }
        })
    }
    props.DOM.footer = $('<div class="footer"></div>');
    for (let i = 0; i < props.buttons.length; i++) {
        let btn = $('<div>' + props.buttons[i].label + '</div>');
        btn.addClass('button hover cursor no-select transition');
        props.DOM.footer.append(btn);
        if (typeof(props.buttons[i].function) === 'function') {
            btn.on('click', {dialog: props}, props.buttons[i].function);
        }
    }
    props.DOM.footer.on('click', props.cleanup);
    dialog.append(props.DOM.header,
                  props.DOM.content,
                  props.DOM.footer);
    props.DOM.dialog.append(dialog).addClass('invisible');
    $(props.parent).append(props.DOM.dialog);
    props.onload({data: {dialog: props}});
    setTimeout(function() {
        props.DOM.dialog.removeClass('invisible');
        if (props.notification) {
            setTimeout(function() {
                props.cleanup();
            }, props.timeout)
        } else if (props.prompt) {
            setTimeout(function() {
                props.value.focus();
            }, 100)
        }
    }, 100);
}
function createRandomDialog(dir) {
    // generates a dialog to choose a number of tracks to randomly add to the tracklist
    createDialog({
        class: "random",
        title: getTranslation('dialog.title.addRandomly'),
        content: `<div class="random">
                      <div class="button hover-bg cursor no-select transition">-</div>
                      <div class="counter">0</div>
                      <div class="button hover-bg cursor no-select transition">+</div>
                      <div class="button hover-bg cursor no-select transition">1</div>
                      <div class="button hover-bg cursor no-select transition">2</div>
                      <div class="button hover-bg cursor no-select transition">3</div>
                      <div class="button hover-bg cursor no-select transition"><</div>
                      <div class="button hover-bg cursor no-select transition">4</div>
                      <div class="button hover-bg cursor no-select transition">5</div>
                      <div class="button hover-bg cursor no-select transition">6</div>
                      <div class="button hover-bg cursor no-select transition">CE</div>
                      <div class="button hover-bg cursor no-select transition">7</div>
                      <div class="button hover-bg cursor no-select transition">8</div>
                      <div class="button hover-bg cursor no-select transition">9</div>
                      <div class="button hover-bg cursor no-select transition">0</div>
                  </div>`,
        onload: function(e) {
            let container = $(e.data.dialog.DOM.content).find('.random');
            container.on('click', '.button', function(e) {
                let button = $(this).html();
                let counter = container.find('.counter');
                let count = counter.html();
                switch (button) {
                    case "-":
                        if (count > 0) {
                            counter.html(parseInt(count) - 1);
                        }
                        break;
                    case "+":
                        if (count < 99999) {
                            counter.html(parseInt(count) + 1);
                        }
                        break;
                    case "CE":
                        counter.html('0');
                        break;
                    case "&lt;":
                        if (count.length > 1) {
                            counter.html(count.substring(0, count.length - 1));
                        } else {
                            counter.html('0');
                        }
                        break;
                    case "0":
                        if (count != '0') {
                            if (count.length < 5) {
                                counter.html(count + button);
                            }
                        }
                        break;
                    default:
                        if (count.length < 5) {
                            if (count == '0') {
                                counter.html(button);
                            } else {
                                counter.html(count + button);
                            }
                        }
                        break;
                }
            });
        },
        onok: function(e) {
            let count = $(e.data.dialog.DOM.content).find('.counter').html();
            if (count > 0) {
                let data = [dir, parseInt(count)];
                sendCmd("tracklist_add_random", data);
            }
        },
        oncancel: function(e) {
            return true;
        }
    });
}
function createThemeDialog() {
    // generates a dialog to change the color theme
    let primaryColor = root.css(themeProps[0]).trim();
    let secondaryColor = root.css(themeProps[1]).trim();
    let hoverColor = root.css(themeProps[2]).trim();
    let primaryColorNew = primaryColor;
    let secondaryColorNew = secondaryColor;
    let hoverColorNew = hoverColor;
    createDialog({
        class: "theme",
        title: getTranslation('dialog.title.localColorTheme'),
        content: `<div class="theme">
                      <p>${getTranslation('dialog.text.primaryColor')}:</p>
                      <div class="primary"></div>
                      <p>${getTranslation('dialog.text.secondaryColor')}:</p>
                      <div class="secondary"></div>
                      <p>${getTranslation('dialog.text.hoverColor')}:</p>
                      <div class="hover"></div>
                  </div>`,
        onload: function(e) {
            let content = $(e.data.dialog.DOM.content);
            let primaryDOM = content.find('.primary');
            let secondaryDOM = content.find('.secondary');
            let hoverDOM = content.find('.hover');
            hideSubbars();
            if (checkMobile()) {
                primaryDOM.append('<input class="button" type="color">');
                primaryDOM.children('input').val(primaryColor)
                .on('change', function(e) {
                    color = $(this).val();
                    primaryColorNew = color;
                    root.css(themeProps[0], primaryColorNew);
                });
                secondaryDOM.append('<input class="button" type="color">');
                secondaryDOM.children('input').val(secondaryColor)
                .on('change', function(e) {
                    color = $(this).val();
                    secondaryColorNew = color;
                    root.css(themeProps[1], secondaryColorNew);
                });
                hoverDOM.append('<input class="button" type="color">');
                hoverDOM.children('input').val(hoverColor)
                .on('change', function(e) {
                    color = $(this).val();
                    hoverColorNew = color;
                    root.css(themeProps[2], hoverColorNew);
                });
            } else {
                let primary = new iro.ColorPicker(primaryDOM[0], {
                    width: 100,
                    color: primaryColor
                });
                primary.on('color:change', function(color) {
                    primaryColorNew = color.hexString;
                    root.css(themeProps[0], primaryColorNew);
                })
                let secondary = new iro.ColorPicker(secondaryDOM[0], {
                    width: 100,
                    color: secondaryColor
                });
                secondary.on('color:change', function(color) {
                    secondaryColorNew = color.hexString;
                    root.css(themeProps[1], secondaryColorNew);
                })
                let hover = new iro.ColorPicker(hoverDOM[0], {
                    width: 100,
                    color: hoverColor
                });
                hover.on('color:change', function(color) {
                    hoverColorNew = color.hexString;
                    root.css(themeProps[2], hoverColorNew);
                })
            }
        },
        onok: function(e) {
            setTheme([
                primaryColorNew,
                secondaryColorNew,
                hoverColorNew
            ]);
            setStorage("theme", JSON.stringify([
                primaryColorNew,
                secondaryColorNew,
                hoverColorNew
            ]));
        },
        oncancel: function(e) {
            setTheme([
                primaryColor,
                secondaryColor,
                hoverColor
            ]);
        },
        buttons: [
            {
                label: 'reset',
                function: function(e) {
                    setTheme([
                        globalData.theme_primary,
                        globalData.theme_secondary,
                        globalData.theme_hover
                    ]);
                    delStorage("theme");
                }
            }
        ]
    });
}
function backButtonHandling() {
    // preset the back button handling on mobile devices  /////////////////beta
    if (checkMobile()) {
        if (!sessionStorage.getItem('alreadyVisited')) {
            sessionStorage.setItem('alreadyVisited', true);
            history.pushState({return: true}, '', '');
        }
        history.forward();
        $(window).on('popstate', function(e) {
            document.title = globalData.pibox_name;
            let goUpper = directoryContent[0];
            if (e.originalEvent.state){
                if (goUpper.properties.type == 'return') {
                    $(goUpper).children('.icon').trigger('click');
                } else {
                    history.go(-2);
                    createToast({
                        message: getTranslation('toast.twiceToExit'),
                        timeout: 1000
                    })
                    $(window).off('popstate');
                }
            } else {
                history.forward();
            }
            return e.preventDefault();
        });
    }
}
function updateDirectory(data) {
    // update directory (folder view)
    contentDOM.css('scroll-behavior', 'auto').scrollTop(0).removeAttr('style');
    toggleReturnSegment();
    clearSearchDirectory();
    clearMarks('directory');
    directoryContent = [];
    globalData.current_path = data.directory;
    pathDOM.html(createPath(data.directory));
    directoryDOM.empty();
    for (let index = 0; index < data.content.length; index++) {
        let segment = data.content[index];
        let settings = {
            type: segment.type,
            data: segment.url,
            name: segment.name
        }
        if (segment.type == "back"){
            settings.type = 'return';
            settings.title = getTranslation('tooltip.return');
            settings.name = getTranslation('misc.segmentReturn');
            settings.icon = 'fa-chevron-circle-left';
        } else if (segment.type == "empty"){
            settings.title = getTranslation('tooltip.empty');
            settings.name = getTranslation('misc.segmentEmpty');
            settings.icon = 'fa-dizzy';
        } else if (segment.type == "dir"){
            settings.title = getTranslation('tooltip.open');
            settings.icon = 'fa-folder';
            if (globalData.current_path != globalData.base_path) {
                settings.context = true;
                settings.markable = true;
            }
        } else if (segment.type == "file"){
            settings.title = getTranslation('tooltip.play');
            settings.icon = 'fa-file-audio';
            settings.command = 'tracklist_play_new';
            settings.context = true;
            settings.markable = true;
        } else if (segment.type == "radio"){
            settings.title = getTranslation('tooltip.play');
            settings.icon = 'fa-podcast';
            settings.command = 'tracklist_play_new';
            settings.context = true;
        } else if (segment.type == "playlist"){
            settings.title = getTranslation('tooltip.play');
            settings.icon = 'fa-file-alt';
            settings.command = 'tracklist_play_new';
            settings.badge = segment.extra.badge;
            settings.context = true;
        }
        let element = createSegment(settings);
        directoryContent.push(element);
    }
    for (let i = 0; i < possibleSegments().total; i++) {
        directoryDOM.append(directoryContent[i]);
    }
    loadingDOM.addClass('invisible');
    setStorage("url", data.directory);
    if (directoryContent[0].properties.type == 'return' && checkMobile()) {
        backButtonHandling();  ////////////////////////////////////////////beta
    }
}
function createPath(path) {
    // create the path dom
    let simplePath = path.replace(globalData.base_path, globalData.pibox_name);
    let folderNames = simplePath.split('\/');
    let segments = [];
    let folderCount = folderNames.length;
    // split path to create an array of objects{name, path}
    for (let i = folderCount - 1; i >= 0; i--) {
        let name = folderNames[i];
        let simplePath = folderNames.slice(0, i + 1).join('\/');
        let path = simplePath.replace(globalData.pibox_name, globalData.base_path);
        segments.unshift({name: name,
                          path: path})
    }
    // create the DOM element
    let wrapper = $('<div></div>');
    let segmentCount = segments.length;
    for (let i = 0; i < segmentCount; i++) {
        let container = $(`<div class="segment no-select"></div>`);
        if (i !== segmentCount - 1) {
            container.attr('onclick', 'void(\'\');');
            container.attr('data-data', segments[i].path);
            container.addClass('jump transition hover-bg cursor');
        }
        let name = $(`<span class="name">${segments[i].name}</span>`);
        container.append(name);
        wrapper.append(container);
    }
    let stringifiedWrapper = wrapper.html();
    return stringifiedWrapper;
}
function createSegment(settings) {
    // creates a single segment for the directory based on the given settings
    /*
    settings {
        type:       string      # the type class for the segment
        title:      string      # the hover title of segments icon
        command:    string      # the command for data-cmd of segments icon
        data:       string      # the data for data-data of segments icon
        icon:       string      # the icon class of segments icon
        context:    boolean     # add class "context-menu" if true
        name:       string      # the name for the segment
        markable:   boolean     # add input checkbox if true
        badge:      int         # adds a badge with the given int
    }
    */
    let props = {
        type: 'undefined',
        title: 'undefined',
        command: undefined,
        data: undefined,
        icon: 'undefined',
        context: false,
        name: 'undefined',
        markable: false,
        badge: undefined
    }
    for (let prop in settings) {
        props[prop] = settings[prop];
    }
    let segment = $('<li class="segment ' + props.type + '"></li>');
    let icon = $('<div title="' + props.title + '" onclick="void(\'\');"></div>');
    icon.addClass('icon hover transition cursor no-select');
    if (props.context) {
        icon.addClass('context-menu');
    }
    if (props.command) {
        icon.attr('data-cmd', props.command);
    }
    if (props.data) {
        icon.attr('data-data', props.data);
    }
    icon.append('<i class="fa fa-5x ' + props.icon + '"></i>');
    segment.append(icon);
    if (props.markable) {
        segment.append('<input type="checkbox" class="mark">');
    }
    if (props.badge) {
        segment.append('<div class="badge">' + props.badge + '</div>');
    }
    segment.append('<div class="name">' + props.name + '</div>');
    segment.properties = props;
    return segment;
}
function possibleSegments() {
    // return how many segments can be display, in X/Y axis and total
    let width = directoryDOM.width();
    let height = $(document).height() - directoryDOM.offset().top;
    let gap = root.css('--directory-gap').trim().replace('px', '');
    let elemX = Math.floor((width - (gap * (Math.floor(width / 100) - 1))) / 100);
    let elemY = Math.floor((height - (gap * (Math.floor(height / 140) - 1))) / 140) + 2;
    return {
        xAxis: elemX,
        yAxis: elemY,
        total: elemX * elemY
    };
}
function toggleReturnSegment(scrolltop) {
    // toggle return segment with scroll-top segment
    let returnDOM = directoryDOM.find('.segment.return .icon');
    if (scrolltop) {
        directoryDOM.addClass('scroll-top');
        returnDOM.attr('title', getTranslation('tooltip.toTop'));
    } else {
        directoryDOM.removeClass('scroll-top');
        returnDOM.attr('title', getTranslation('tooltip.return'));
    }
}
function searchDirectory(search) {
    // search in directory
    toggleReturnSegment();
    directoryDOM.empty();
    for (let i = 0; i < directoryContent.length; i++) {
        directoryDOM.append(directoryContent[i]);
    }
    directorySearch.reIndex();
    if (searchDOM.hasClass('slidedown')) {
        searchDOM.removeClass('slidedown');
    }
    directorySearch.search(search);
    if (directoryContent[0].properties.type == "return") {
        directoryDOM.prepend(directoryContent[0]);
    }
}
function clearSearchDirectory() {
    // clear and reset the file search
    if (searchBadgeDOM.text() != "") {
        directorySearch.search();
        searchIconDOM.attr('title', getTranslation('tooltip.search'))
                     .children('i').toggleClass('fa-search-minus');
        searchBadgeDOM.hide().text('');
    }
    if (searchDOM.hasClass('slidedown')) {
        searchDOM.removeClass('slidedown');
    }
}
function updateModebutton(mode) {
    // update playmode button
    let settings = {};
    if (mode == "normal") {
        settings.title = getTranslation('tooltip.modeNormal');
        settings.icon = 'fa-exchange-alt';
    } else if (mode == "shuffle") {
        settings.title = getTranslation('tooltip.modeRandom');
        settings.icon = 'fa-random';
    } else if (mode == "loop") {
        settings.title = getTranslation('tooltip.modeLoop');
        settings.icon = 'fa-sync-alt';
    }
    modeButtonDOM.attr('title', settings.title);
    modeButtonIconDOM.removeAttr('class')
                     .addClass('fa fa-2x ' + settings.icon);
}
function updateVolume(volume) {
    // update volume informations
    globalData.volume = volume;
    sidebarDOM.find('.button.volume .badge').text(globalData.volume);
}
function updateCurrent(data) {
    // update current title informations
    clearTimeout(progressInterval);
    globalCurrent = data;
    let settings;
    switch(globalCurrent.state) {
        case "stop":
            settings = {
                docTitle: globalData.pibox_name
            };
            break;
        case "load":
            settings = {
                icon: 'fa-hourglass',
                title: getTranslation('misc.loading'),
                docTitle: getTranslation('misc.loading'),
                buttonTitle: getTranslation('tooltip.load')
            };
            break;
        case "pause":
        case "play":
            settings = {
                position: getDuration(globalCurrent.position)
            }
            if(globalCurrent.duration == 0) {
                settings.duration = '\u221E:\u221E';
                settings.infinite = true;
            } else {
                settings.duration = getDuration(globalCurrent.duration);
                settings.progress = Math.floor((globalCurrent.position * 100) / globalCurrent.duration);
                settings.seekable = true;
            }
            if (globalCurrent.mrl.startsWith('http')) {
                settings.index = getTranslation('misc.stream');
            } else {
                settings.index = (globalCurrent.index + 1)  + '.';
            }
            let title;
            if (globalCurrent.artist == null) {
                title = globalCurrent.title;
            } else {
                title = globalCurrent.artist + ' - ' + globalCurrent.title;
            }
            settings.title = title;
            if (globalCurrent.state === 'pause') {
                settings.icon = 'fa-pause';
                settings.docTitle = '\u275A\u275A ' + title;
            } else if (globalCurrent.state === 'play') {
                settings.icon = 'fa-play';
                settings.docTitle = '\u25B6 ' + title;
                settings.buttonTitle = getTranslation('tooltip.pause');
                settings.buttonIcon = 'fa-pause';
                progressInterval = setTimeout(function() {
                    sendCmd('player_get_current');
                }, 100);
            };
            break;
        default:
            console.log('unkown state');
    }
    updateTitleInfo(settings);
    if (['play', 'pause'].includes(globalCurrent.state)) {
        if (globalCurrent.mrl != backupCurrent.mrl &&
            globalTracklist.length > 0 &&
            root.css("--tracklist-marker").trim() == 'hidden' &&
            !tracklistSearch.searched &&
            globalCurrent.index >= 0) {
                backupCurrent = globalCurrent;
                let offset = $('#tracklist .list .track').first().position().top;
                let elem = "#tracklist .list .track[data-data='"+globalCurrent.index+"']";
                $('#tracklist .list').scrollTop($(elem).position().top - offset);
        }
    }
}
function updateTitleInfo(settings) {
    // update the title informations
    let props = {
        position: '00:00',
        progress: '0',
        infinite: false,
        seekable: false,
        duration: '00:00',
        icon: 'fa-stop',
        index: '',
        title: '',
        docTitle: '',
        buttonTitle: getTranslation('tooltip.play'),
        buttonIcon: 'fa-play'
    }
    for (let prop in settings) {
        props[prop] = settings[prop];
    }
    if (positionDOM.text() != props.position) {
        positionDOM.text(props.position);
    }
    progressDOM.val(props.progress / 100)
               .attr('value' , props.progress)
               .css('--progress', props.progress + '%');
    if (props.infinite) {
        progressDOM.addClass('infinite');
    } else {
        progressDOM.removeClass('infinite');
    }
    if (props.seekable) {
        progressDOM.prop('disabled', false)
                   .addClass('cursor');
    } else {
        progressDOM.prop('disabled', true)
                   .removeClass('cursor');
    }
    if (durationDOM.text() != props.duration) {
        durationDOM.text(props.duration);
    }
    stateIconDOM.removeAttr('class')
                .addClass('fa ' + props.icon);
    if (stateTitleTextDOM.text() != props.title ||
        stateIndexDOM.text() != props.index) {
        stateTitleDOM.removeClass('scrolling');
        stateIndexDOM.text(props.index);
        stateTitleTextDOM.text(props.title)
                         .attr('title', props.title);
    }
    if (document.title != props.docTitle) {
        document.title = props.docTitle;
    }
    if (stateTitleTextDOM.width() > (stateInfoDOM.width() - stateIndexDOM.width()) ||
        stateTitleTextDOM[0].scrollWidth > stateTitleTextDOM[0].clientWidth) {
        stateTitleDOM.addClass('scrolling');
    }
    stateButtonDOM.attr('title', props.buttonTitle);
    stateButtonIconDOM.removeAttr('class')
                      .addClass('fa fa-2x ' + props.buttonIcon);
}
function updateTracklist(tracklist) {
    // update the tracklist
    globalTracklist = tracklist;
    let totalDuration = 0;
    let tracklistSearched = tracklistSearch.searched;
    let tracklistCheckedMarker = [];
    tracklistDOM.find('.mark').each(function(index, elem) {
        if ($(this).prop('checked')) {
            tracklistCheckedMarker.push(index);
        }
    })
    tracklistListDOM.empty();
    for (let index = 0; index < globalTracklist.length; index++) {
        let segment = globalTracklist[index];
        totalDuration += segment.duration;
        let settings = {
            mrl: segment.mrl,
            data: segment.index,
            index: segment.index,
            artist: segment.artist,
            title: segment.title,
            duration: segment.duration,
        }
        if(segment.index == globalCurrent.index && globalCurrent.state != "stop"){
            settings.state = 'playing';
            if (globalCurrent.state == 'pause') {
                settings.state += ' paused';
            }
        }
        let element = createTracklistSegment(settings);
        tracklistListDOM.append(element);
    }
    tracklistBadgeDOM.text(globalTracklist.length);
    tracklistListHeaderDurationDOM.text(getDuration(totalDuration));
    if (globalTracklist.toString() == backupTracklist.toString() && tracklistCheckedMarker.length > 0) {
            let tracklistMarker = tracklistDOM.find('.mark');
            for (let i = 0; i < tracklistCheckedMarker.length; i++) {
                $(tracklistMarker[tracklistCheckedMarker[i]]).prop('checked', true);
            }
    } else {
        tracklistSearch.reIndex();
        clearMarks('tracklist');
    }
    if (tracklistSearched) {
        tracklistSearch.search(tracklistHeaderSearchDOM.attr('data-value'));
    }
    backupTracklist = globalTracklist;
}
function createTracklistSegment(settings) {
    // creates a single segment for the tracklist based on the given settings
    /*
    settings {
        mrl:       string      # the mrl path for the segment
        data:      string      # the data for data-data of segments icon
        index:     integer     # the index of the segment
        artist:    string      # the artist of the segment
        title:     string      # the title of the segment
        duration:  integer     # add duration of the segment
        state:     string      # the playing state of the segment
    }
    */
    let props = {
        mrl: 'undefined',
        data: undefined,
        index: 0,
        artist: 'undefined',
        title: 'undefined',
        duration: 0,
        state: ''
    }
    for (let prop in settings) {
        props[prop] = settings[prop];
    }
    let segment = $('<li class="track ' + props.state + '"></li>');
    segment.addClass('hover-bg transition cursor no-select context-menu');
    segment.attr('title', props.mrl);
    segment.attr('data-cmd', "tracklist_play_index");
    segment.attr('data-data', props.data);
    segment.append('<span class="index">' + (props.index + 1) + '.</span>');
    if (props.artist == null) {
        props.info = props.title;
    } else {
        props.info = '<b>' + props.artist.toUpperCase() + '</b> - ' + props.title;
    }
    segment.append('<span class="title">' + props.info + '</span>');
    segment.append('<span class="duration">' + getDuration(props.duration) + '</span>');
    segment.append('<input type="checkbox" class="mark">');
    segment.properties = props;
    return segment;
}
function clearSearchTracklist() {
    // clear and reset the tracklist search
    if (tracklistHeaderSearchDOM.children('span').text() != "") {
        tracklistSearch.search();
        tracklistHeaderSearchDOM.attr('title', getTranslation('tooltip.search'))
                                .removeAttr('data-value');
        tracklistHeaderSearchDOM.children('i').removeClass('fa-search-minus');
        tracklistHeaderSearchDOM.children('span').text('')
    }
}
function readConfig() {
    // insert settings to the config menu
    configDOM.find('.list .setting').each(function(index, elem) {
        let elemDOM = $(elem);
        let keyValue = globalData[elemDOM.children('.value').attr("data-key")];
        if (typeof(keyValue) === "boolean") {
            elemDOM.children('.value').prop('checked', keyValue);
            let subConfig = $('.' + elemDOM.children('.value').attr("data-class"));
            if (keyValue == true) {
                subConfig.show();
            } else {
                subConfig.hide();
            }
        } else {
            elemDOM.children('.value').val(keyValue);
        }
    });
}
function writeConfig() {
    // write changed configuration to global configuration
    configDOM.find('.list .setting').each(function(index, elem) {
        let elemDOM = $(elem);
        let elemInput = elemDOM.children('.value');
        let elemType = elemInput.attr('type');
        let keyValue;
        if (elemType === 'checkbox') {
            keyValue = elemInput.prop( "checked" );
        } else if (elemType === 'number') {
            keyValue = Number(elemInput.val());
        } else {
            keyValue = elemInput.val();
        }
        globalData[elemInput.attr("data-key")] = keyValue;
    });
}
function hideSubwindows() {
    // hide the opened subwindows
    subWindowsDOM.hide();
}
function valMarks(selector, elem) {
    // return the specific objects either for directory or tracklist multi select
    let props = {};
    switch (selector) {
        case 'directory':
            props.rootProperty = '--file-marker';
            props.activeMarker = $(elem).parent().children('.mark');
            props.checkboxes = contentDOM.find('.directory .segment .mark');
            props.checkedBoxes = contentDOM.find('.directory .segment .mark:checked');
            break;
        case 'tracklist':
            props.rootProperty = '--tracklist-marker';
            props.activeMarker = $(elem).children('.mark');
            props.checkboxes = tracklistDOM.find('.list .track .mark');
            props.checkedBoxes = tracklistDOM.find('.list .track .mark:checked');
            break;
        default:
            console.log('unkown selector');
    }
    return props;
}
function showMarks(elem, selector) {
    // show up the marks for multi select, either directory or tracklist
    let props = valMarks(selector, elem);
    if (root.css(props.rootProperty).trim() == 'hidden') {
        root.css(props.rootProperty, 'visible');
    }
    props.activeMarker.prop('checked', true).trigger('input');
}
function playMarks() {
    // play new files based on the multi select, for directory only
    let props = valMarks('directory');
    let files = [];
    props.checkedBoxes.each(function(index, value) {
        files.push($(this).siblings(".icon").attr("data-data"));
    });
    sendCmd('tracklist_play_new', files);
    clearMarks('directory');
}
function addMarks() {
    // add files to tracklist based on the multi select, for directory only
    let props = valMarks('directory');
    let files = [];
    props.checkedBoxes.each(function(index, value) {
        files.push($(this).siblings(".icon").attr("data-data"));
    });
    sendCmd('tracklist_add', files);
    clearMarks('directory');
}
function delMarks() {
    // delete tracks from tracklist based on the multi select, for tracklist only
    let props = valMarks('tracklist');
    let indecies = [];
    props.checkedBoxes.each(function(index, value) {
        indecies.push($(this).parent().attr("data-data"));
    });
    sendCmd('tracklist_remove_index', indecies);
    sendCmd('player_get_current');
    clearMarks('tracklist');
}
function allMarks(marker) {
    // select all possible elements, for directory and tracklist
    let props = valMarks(marker);
    props.checkboxes.each(function(index, value) {
        $(this).prop('checked', true);
    });
    props.checkboxes.first().trigger('input');
}
function clearMarks(marker) {
    // cancel all selections, for directory and tracklist
    let props = valMarks(marker);
    props.checkedBoxes.each(function(index, value) {
        $(this).prop('checked', false);
    });
    root.css(props.rootProperty, 'hidden');
    props.checkboxes.first().trigger('input');
}
function createToast(settings) {
    // show a toast notification
    /*
    settings {
        parent:     string      # parent object to append the dialog
        message:    string      # the message of the toast
        timeout:    int         # time in ms for autoclose the toast
    }
    */
    let props = {
        parent: '#layout',
        DOM: undefined,
        message: 'undefinded',
        timeout: 3000
    }
    for (let prop in settings) {
        props[prop] = settings[prop];
    }
    $('#toast').each(function() {
        $(this).detach();
    })
    props.DOM = $('<div id="toast"></div>');
    props.DOM.html(props.message)
             .addClass('invisible');
    $(props.parent).append(props.DOM);
    setTimeout(function() {
        props.DOM.removeClass('invisible');
        setTimeout(function() {
            props.DOM.addClass('invisible');
            setTimeout(function() {
                props.DOM.detach();
            }, 500);
        }, props.timeout);
    }, 100);
}
function attachEventListener() {
    // WINDOW EVENTS //
    $(window).on('message', function(e) {
        // WINDOW: receive message
        let data = e.originalEvent.data;
        switch(data) {
            case "close":
                websocket.close();
                break;
            default:
                break;
        }
    })
    .on('resize', function(e) {
        // WINDOW: change size or orientation
        if (['play', 'pause'].includes(globalCurrent.state)) {
            topbarDOM.find('.title').removeClass('scrolling');
            sendCmd('player_get_current');
        }
    })
    .on('beforeunload', function(e) {
        // WINDOW: before unload
        websocket.close();
    });
    // LOGO EVENTS //
    logoDOM.on('click', function(e) {
        // LOGO: print infomations
        console.log(globalData);
        console.log(dictionary);
        createDialog({
            class: 'version',
            alert: true,
            content:`<div class="version">
                        <div>PiBox Version:</div><div>${globalData.version}</div>
                        <div>HTML Version:</div><div>${versions.html}</div>
                        <div>CSS Version:</div><div>${versions.css}</div>
                        <div>JS Version:</div><div>${versions.js}</div>
                    <div>`
        })
    });
    // TOPBAR EVENTS //
    topbarDOM.on('input', '.progress', function(e) {
        // TOPBAR: progress seek
        clearTimeout(progressInterval);
        $(this).css('--progress', e.originalEvent.target.valueAsNumber*100 + '%');
        let time = ((e.originalEvent.target.valueAsNumber*100)*globalCurrent.duration)/100;
        positionDOM.html(getDuration(time));
    })
    .on('mouseup touchend', '.progress', function(e) {
        // TOPBAR: progress send position
        if ($(this).is(':enabled')) {
            sendCmd('player_set_position', e.originalEvent.target.valueAsNumber);
            sendCmd('player_get_current');
        }
    });
    // SIDEBAR EVENTS //
    sidebarDOM.on('click', '.button', function(e) {
        // SIDEBAR: button handling
        let button = $(this);
        let cmd = button.attr("data-cmd");
        if (cmd == undefined || cmd == false) {
            return false
        }
        let data = button.attr("data-data");
        if (data == undefined || data == false) {
            data = "";
        }
        sendCmd(cmd, data);
    })
    .on('click', '.button.home', function(e) {
        // SIDEBAR: home button
        hideSubwindows();
        sendCmd("system_get_directory", globalData.base_path);
    })
    .on('click', '.button.tracklist', function(e) {
        // SIDEBAR: show/hide tracklist
        if (tracklistDOM.is(":visible")) {
            tracklistDOM.hide()
            clearMarks('tracklist');
            clearSearchTracklist();
        } else {
            hideSubbars();
            hideSubwindows();
            tracklistDOM.show()
            if (['play', 'pause'].includes(globalCurrent.state)) {
                if (globalCurrent.index >= 0) {
                    let firstTrack = tracklistDOM.find('.track').first().position().top;
                    let currentTrack = tracklistDOM.find('.track[data-data='+globalCurrent.index+']')
                                       .position().top;
                    tracklistListDOM.scrollTop(currentTrack - firstTrack);
                }
            }
        };
    })
    .on('click', '.button.theme', function(e) {
        // SIDEBAR: change local color theme
        createThemeDialog();
    })
    .on('click', '.button.tts', function(e) {
        // SIDEBAR: text to speech
        createDialog({
            content: getTranslation('dialog.text.textToSpeech'),
            prompt: true,
            onok: function(e) {
                let value = e.data.dialog.value.val();
                if (value == "") {
                    return true;
                }
                let url = 'https://translate.google.com/translate_tts?ie=UTF-8&client=tw-ob&tl=De-de&q='+
                          encodeURI(value);
                sendCmd('tracklist_play_new', url);
            }
        })
    })
    .on('click', '.button.stream', function(e) {
        // SIDEBAR: direct http stream url
        createDialog({
            content: getTranslation('dialog.text.streamAddress'),
            width: 350,
            prompt: true,
            placeholder: 'https://www.youtube.com/watch?v=YE7VzlLtp-4',
            onok: function(e) {
                let value = e.data.dialog.value.val();
                if (value == "") {
                    return true;
                }
                sendCmd('tracklist_play_new', value);
            }
        })
    })
    .on('click', '.button.config', function(e) {
        // SIDEBAR: show configuration
        if (!configDOM.is(":visible")) {
            hideSubbars();
            hideSubwindows();
            configDOM.show();
        };
    })
    .on('click', '.button.reload', function(e) {
        // SIDEBAR: reload pibox program
        createDialog({
            content: getTranslation('dialog.text.scriptReload'),
            onok: function(e) {
                showLoading();
                sendCmd('system_reload');
            },
            labelok: getTranslation('dialog.button.yes'),
            labelcancel: getTranslation('dialog.button.no')
        })
    })
    .on('click', '.button.restart', function(e) {
        // SIDEBAR: reboot device, need root privileges
        createDialog({
            content: getTranslation('dialog.text.systemReboot'),
            onok: function(e) {
                showLoading();
                sendCmd('system_reboot');
            },
            labelok: getTranslation('dialog.button.yes'),
            labelcancel: getTranslation('dialog.button.no')
        })
    })
    .on('click', '.button.shutdown', function(e) {
        // SIDEBAR: shutdown device, need root privileges
        createDialog({
            content: getTranslation('dialog.text.systemShutdown'),
            onok: function(e) {
                showLoading();
                sendCmd('system_shutdown');
            },
            labelok: getTranslation('dialog.button.yes'),
            labelcancel: getTranslation('dialog.button.no')
        })
    })
    .on('click', '.button.subbar', function(e) {
        // SIDEBAR: show subbar
        let button = $(this);
        let subBar = button.children('.subbar');
        if (!subBar.is(":visible")) {
            let options = {
                "my": "left top-4",
                "at": "right top",
                "of": this
            };
            let overlay = $('<div class="subbar-overlay" onclick="void(\'\');"></div>');
            button.before(overlay);
            button.removeClass('hover');
            subBar.show().position(options);
        }
    })
    .on('click', '.subbar-overlay', function() {
        // SIDEBAR: submenu hide
        hideSubbars();
    })
    .on('mousedown touchstart', '.button.volup, .button.voldown', function(e) {
        // SIDEBAR: hold volume button
        let cmd = $(this).attr('data-cmd');
        volumeButtonHold = setTimeout(function() {
            volumeButtonStep = setInterval(function() {
                sendCmd(cmd);
            }, 300);
        }, 500);
    })
    .on('mouseup mouseleave touchend touchmove', '.button.volup, .button.voldown', function(e) {
        // SIDEBAR: release volume button
        clearInterval(volumeButtonStep);
        clearTimeout(volumeButtonHold);
    });
    // CONTENT EVENTS //
    contentDOM.on('scroll', function(e) {
        // CONTENT: handle events if content larger than viewable area
        let returnDOM = directoryDOM.find('.segment.return .icon');
        let shownSegments = directoryDOM.children('.segment');
        let visibleHeight = contentDOM.innerHeight();
        let contentHeight = pathDOM.height() + directoryDOM.height();
        let spaceToBottom = (contentHeight - visibleHeight) - contentDOM.scrollTop();
        let spaceFromTop = contentDOM.scrollTop();
        if (contentHeight > visibleHeight) {
            // toggle return segment with scroll-top segment
            if (spaceFromTop >= 80) {
                toggleReturnSegment(true);
            } else {
                toggleReturnSegment();
            }
            // better performance on mobile devices by adding segments on scroll
            if (spaceToBottom <= 140) {
                if (shownSegments.length < directoryContent.length) {
                    for (let i = 0; i < possibleSegments().xAxis; i++) {
                        let index = shownSegments.length + i;
                        directoryDOM.append(directoryContent[index]);
                    }
                }
            }
            // move search button if overlap a segment
            if (!directorySearch.searched) {
                if (spaceToBottom <= 0) {
                    let searchOverlap = shownSegments.length % possibleSegments().xAxis;
                    if (searchOverlap == 0) {
                        searchDOM.addClass('slidedown');
                    }
                } else {
                    searchDOM.removeClass('slidedown');
                }
            } else {
                searchDOM.removeClass('slidedown');
            }
        }
    })
    .on('click', '.path .segment.jump', function(e) {
        // CONTENT: quick jump to folder
        showLoading(false);
        sendCmd("system_get_directory", $(this).attr('data-data'));
    })
    .on('click', '.directory .segment.return .icon', function(e) {
        // CONTENT: back/scroll-top segment
        let segment = $(this);
        if ($(segment.parents()[1]).hasClass('scroll-top')) {
            contentDOM.scrollTop(0);
        } else {
            let path = segment.attr('data-data');
            showLoading(false);
            sendCmd("system_get_directory", path);
        }
    })
    .on('click', '.directory .segment.dir .icon', function(e) {
        // CONTENT: open folder
        let segment = $(this);
        let path = segment.attr('data-data');
        showLoading(false);
        sendCmd("system_get_directory", path);
    })
    .on('click', '.directory .segment.file .icon, .segment.radio .icon,' +
                 '.segment.playlist .icon', function(e) {
        // CONTENT: play file
        let segment = $(this);
        let cmd = segment.attr('data-cmd');
        let path = segment.attr('data-data');
        sendCmd(cmd, path);
    })
    .on('click', '.directory .segment.empty .icon', function(e) {
        // CONTENT: show warning if folder is empty
        createDialog({
            content: getTranslation('dialog.text.emptyFolder'),
            alert: true
        })
    })
    .on('input', '.directory .segment .mark', function(e) {
        // CONTENT: count respectively hide multi select
        let checkboxes = contentDOM.find('.mark:checked');
        if (checkboxes.length == 0) {
            root.css('--file-marker', 'hidden');
        }
    });
    // SEARCH EVENTS //
    searchDOM.on('click', function(e) {
        // SEARCH: search in directory
        if (searchBadgeDOM.text() != "") {
            clearSearchDirectory();
            sendCmd("system_get_directory", globalData.current_path);
        } else {
            createDialog({
                content: getTranslation('dialog.text.search'),
                prompt: true,
                onok: function(e) {
                    let value = e.data.dialog.value.val();
                    if (value == "") {
                        return true;
                    }
                    searchDirectory(value);
                    searchIconDOM.attr('title', getTranslation('tooltip.clearSearch'))
                                 .children('i').toggleClass('fa-search-minus');
                    searchBadgeDOM.text('"'+value+'"').show();
                }
            })
        }
    });
    // TRACKLIST EVENTS //
    tracklistDOM.on('click', '.close', function(e) {
        // TRACKLIST: hide tracklist
        tracklistDOM.hide();
        clearMarks('tracklist');
        clearSearchTracklist();
    })
    .on('click', '.header .button.search', function(e) {
        // TRACKLIST: search in tracklist
        let button = $(this);
        if(tracklistSearch.size() > 0) {
            if (button.children('span').text() != "") {
                clearSearchTracklist();
            } else {
                createDialog({
                    content: getTranslation('dialog.text.search'),
                    prompt: true,
                    onok: function(e) {
                        let value = e.data.dialog.value.val();
                        if (value == "") {
                            return true;
                        }
                        tracklistSearch.search(value);
                        button.attr('title', getTranslation('tooltip.clearSearch'))
                              .attr('data-value', value);
                        button.children('i').addClass('fa-search-minus');
                        button.children('span').text('"'+value+'"')
                    }
                })
            }
        }
    })
    .on('click', '.header .button.sort-numeric', function(e) {
        // TRACKLIST: sort by numbers (low -> high)
        if(tracklistSearch.size() > 0) {
            tracklistSearch.sort('index');
        }
    })
    .on('click', '.header .button.sort-alphabetic', function(e) {
        // TRACKLIST: sort by names (A -> Z)
        if(tracklistSearch.size() > 0) {
            tracklistSearch.sort('title');
        }
    })
    .on('click', '.header .button.clear', function(e) {
        // TRACKLIST: erase the whole tracklist
        let button = $(this);
        if(tracklistSearch.size() > 0) {
            createDialog({
                content: getTranslation('dialog.text.clearList'),
                onok: function(e) {
                    sendCmd(button.attr('data-cmd'));
                },
                labelok: 'ja',
                labelcancel: 'nein'
            })
        }
    })
    .on('click', '.header .button.save', function(e) {
        // TRACKLIST: save the current tracklist
        let button = $(this);
        if(tracklistSearch.size() > 0) {
            createDialog({
                content: getTranslation('dialog.text.saveList'),
                prompt: true,
                onok: function(e) {
                    var value = e.data.dialog.value.val();
                    if (value == "") {
                        return true;
                    }
                    sendCmd(button.attr('data-cmd'), value);
                }
            })
        }
    })
    .on('click', '.list .track', function(e) {
        // TRACKLIST: play index
        if (root.css('--tracklist-marker').trim() == 'hidden') {
            let track = $(this);
            let cmd = track.attr('data-cmd');
            let index = track.attr('data-data');
            sendCmd(cmd, index);
        }
    })
    .on('input', '.list .track .mark', function(e) {
        // TRACKLIST: count respectively hide multi select
        let checkboxes = tracklistDOM.find('.mark:checked');
        if (checkboxes.length == 0) {
            root.css('--tracklist-marker', 'hidden');
            tracklistListHeaderCenterDOM.text(getTranslation('textContent.tracklistTitle'));
            tracklistListHeaderCountDOM.text('');
        } else {
            tracklistListHeaderCenterDOM.text(getTranslation('textContent.tracklistSelected'));
            tracklistListHeaderCountDOM.text(checkboxes.length + '/' + globalTracklist.length);
        };
    });
    // CONFIG EVENTS //
    configDOM.on('click', '.close', function(e) {
        // CONFIG: hide configuration
        if (changedConfig) {
            createDialog({
                content: getTranslation('dialog.text.optionsChanged'),
                onok: function(e) {
                    configDOM.hide();
                    writeConfig();
                    readConfig();
                    showLoading();
                    sendCmd("system_change_config", globalData);
                    window.changedConfig = true;
                },
                oncancel: function(e) {
                    configDOM.hide();
                    readConfig();
                },
                labelok: getTranslation('dialog.button.yes'),
                labelcancel: getTranslation('dialog.button.no')
            })
        } else {
            configDOM.hide();
        }
        changedConfig = false;
    })
    .on('change', '.list .setting .value', function(e) {
        // CONFIG: configuration has changed
        if (!changedConfig) {
            changedConfig = true;
        }
    })
    .on('change', '.list .setting .value[type="checkbox"]', function(e) {
         // CONFIG: checkbox clicked show sub config
        let subClass = '.' + $(this).attr('data-class');
        let setting = $(this).parent().siblings(subClass);
        if ($(this).is(':checked')) {
            setting.show();
        } else {
            setting.hide();
        }
    });
    // DEVICE SPECIFIC EVENTS //
    if (/iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream) {
        $(document).on('touchstart', '.context-menu', function(e){
             // rightclick handler for iOS
            longpress = setTimeout(function(){
                let x = e.originalEvent.touches[0].pageX;
                let y = e.originalEvent.touches[0].pageY;
                let elem = document.elementFromPoint(x, y);
                $(elem).trigger("contextmenu");
            }, 800);
        })
        .on('touchend touchmove', '.context-menu',function(){
            // rightclick clear
            clearTimeout(longpress);
        });
    }
}
function attachContextMenus() {
    // CONTEXT MENUS //
    $.contextMenu({
        // context: directory
        selector: '.segment.dir .context-menu',
        zIndex: 50,
        animation: {duration: 0, show: 'show', hide: 'hide'},
        callback: function(key, options) {
            sendCmd(key, $(this).attr('data-data'));
        },
        items: {
            tracklist_play_new: {
                name: getTranslation('context.play'),
                icon: "fa-play"
            },
            tracklist_add: {
                name: getTranslation('context.queue'),
                icon: "fa-plus-square"
            },
            separator: {
                type: "cm_separator"
            },
            mark: {
                name: getTranslation('context.select'),
                icon: "fa-check-square",
                callback: function(key, options) {
                    showMarks(this, 'directory');
                }
            },
            separator2: {
                type: "cm_separator"
            },
            tracklist_random: {
                name: getTranslation('context.random'),
                icon: "fa-dice",
                callback: function(key, options) {
                    createRandomDialog($(this).attr('data-data'));
                }
            },
        }
    });
    $.contextMenu({
        // context: mp3 files
        selector: '.segment.file .context-menu',
        zIndex: 50,
        animation: {duration: 0, show: 'show', hide: 'hide'},
        callback: function(key, options) {
            sendCmd(key, $(this).attr('data-data'));
        },
        items: {
            tracklist_play_new: {
                name: getTranslation('context.play'),
                icon: "fa-play"
            },
            tracklist_add: {
                name: getTranslation('context.queue'),
                icon: "fa-plus-square"
            },
            separator: {
                type: "cm_separator"
            },
            mark: {
                name: getTranslation('context.select'),
                icon: "fa-check-square",
                callback: function(key, options) {
                    showMarks(this, 'directory');
                }
            }
        }
    });
    $.contextMenu({
        // context: mp3 files on multiselect
        selector: '.segment.file .mark, .segment.dir .mark',
        zIndex: 50,
        animation: {duration: 0, show: 'show', hide: 'hide'},
        items: {
            tracklist_play_new: {
                name: getTranslation('context.play'),
                icon: "fa-play",
                callback: function(key, options) {
                    playMarks();
                }
            },
            tracklist_add: {
                name: getTranslation('context.queue'),
                icon: "fa-plus-square",
                callback: function(key, options) {
                    addMarks();
                }
            },
            separator1: {
                type: "cm_separator"
            },
            mark_all: {
                name: getTranslation('context.selectAll'),
                icon: "fa-check-double",
                callback: function(key, options) {
                    allMarks('directory');
                }
            },
            separator2: {
                type: "cm_separator"
            },
            mark_clear: {
                name: getTranslation('context.cancel'),
                icon: "fa-times",
                callback: function(key, options) {
                    clearMarks('directory');
                }
            }
        }
    });
    $.contextMenu({
        // context: radio files
        selector: '.segment.radio .context-menu',
        zIndex: 50,
        animation: {duration: 0, show: 'show', hide: 'hide'},
        callback: function(key, options) {
            sendCmd(key, $(this).attr('data-data'));
        },
        items: {
            tracklist_play_new: {
                name: getTranslation('context.play'),
                icon: "fa-play"
            }
        }
    });
    $.contextMenu({
        // context: m3u playlist files
        selector: '.segment.playlist .context-menu',
        zIndex: 50,
        animation: {duration: 0, show: 'show', hide: 'hide'},
        callback: function(key, options) {
            sendCmd(key, $(this).attr('data-data'));
        },
        items: {
            tracklist_play_new: {
                name: getTranslation('context.play'),
                icon: "fa-play"
            },
            tracklist_add: {
                name: getTranslation('context.queue'),
                icon: "fa-plus-square"
            },
            separator: {
                type: "cm_separator"
            },
            system_rename_m3u: {
                name: getTranslation('context.rename'),
                icon: "fa-edit",
                callback: function(key, options) {
                    let oldName = $(this).siblings('.name').text();
                    let url = $(this).attr('data-data');
                    createDialog({
                        content: getTranslation('dialog.text.renameList'),
                        prompt: true,
                        placeholder: oldName,
                        onok: function(e) {
                            let value = e.data.dialog.value.val();
                            if (value == "") {
                                return true;
                            }
                            let data = [url, value]
                            sendCmd(key, data);
                        }
                    })
                }
            },
            system_delete_m3u: {
                name: getTranslation('context.remove'),
                icon: "fa-trash-alt",
                callback: function(key, options) {
                    let url = $(this).attr('data-data');
                    let title = $(this).siblings('.name').html();
                    createDialog({
                        content: getTranslation(['dialog.text.removeList', title]),
                        onok: function(e) {
                            sendCmd(key, url);
                        },
                        labelok: getTranslation('dialog.button.yes'),
                        labelcancel: getTranslation('dialog.button.no')
                    })
                }
            }
        }
    });
    $.contextMenu({
        // context: tracklist items
        selector: '#tracklist .list .context-menu',
        zIndex: 50,
        animation: {duration: 0, show: 'show', hide: 'hide'},
        callback: function(key, options) {
            sendCmd(key, $(this).attr('data-data'));
        },
        items: {
            tracklist_play_index: {
                name: getTranslation('context.play'),
                icon: "fa-play"
            },
            tracklist_remove_index: {
                name: getTranslation('context.remove'),
                icon: "fa-trash-alt"
            },
            separator: {
                type: "cm_separator"
            },
            mark: {
                name: getTranslation('context.select'),
                icon: "fa-check-square",
                callback: function(key, options) {
                    showMarks(this, 'tracklist');
                }
            }
        }
    });
    $.contextMenu({
        // context: tracklist items on multiselect
        selector: '#tracklist .list .track .mark',
        zIndex: 50,
        animation: {duration: 0, show: 'show', hide: 'hide'},
        items: {
            tracklist_remove_index: {
                name: getTranslation('context.remove'),
                icon: "fa-trash-alt",
                callback: function(key, options) {
                    delMarks();
                }
            },
            separator1: {
                type: "cm_separator"
            },
            mark_all: {
                name: getTranslation('context.selectAll'),
                icon: "fa-check-double",
                callback: function(key, options) {
                    allMarks('tracklist');
                }
            },
            separator2: {
                type: "cm_separator"
            },
            mark_clear: {
                name: getTranslation('context.cancel'),
                icon: "fa-times",
                callback: function(key, options) {
                    clearMarks('tracklist');
                }
            }
        }
    });
}

// MAIN //

// request default values and open the websocket when all done
$.ajax({
    dataType: "json",
    url: "/defaults"
}).fail(() => {
    console.log('%c>>> Error while loading defaults', logCSSError);
}).done((data) => {
    // declare global variables
    declareGlobVars();
    // write default values in global data
    globalData = data;
    // set theme color to theme cookie or global theme
    updateTheme();
    // translate the DOM
    initTranslation(globalData.language).always(() => {
        // translate DOM elements
        translateDOM()
        // initialize websocket connection
        initWebsocket();
        // preset back button handling on mobile devices
        backButtonHandling();
        // attach all event listener to the dom
        attachEventListener();
        // attach all context menus to the dom
        attachContextMenus();
    });
});
