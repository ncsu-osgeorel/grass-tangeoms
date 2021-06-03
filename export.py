# -*- coding: utf-8 -*-
"""
@brief GUI panel for export functionality

This program is free software under the GNU General Public License
(>=v2). Read the file COPYING that comes with GRASS for details.

@author: Anna Petrasova (akratoc@ncsu.edu)
"""
import os
import wx
import wx.lib.filebrowsebutton as filebrowse
from gui_core.gselect import Select
from grass.pydispatch.signal import Signal

from tangible_utils import get_show_layer_icon


class OutputPanel(wx.Panel):
    def __init__(self, parent, giface, settings):
        wx.Panel.__init__(self, parent)
        self.giface = giface
        self.settings = settings
        self.settingsChanged = Signal('OutputPanel.settingsChanged')

        if 'output' not in self.settings:
            self.settings['output'] = {}
            self.settings['output']['scan'] = 'scan'
            self.settings['output']['calibration_scan'] = 'scan_saved'
            self.settings['output']['calibrate'] = False
            self.settings['output']['PLY'] = False
            self.settings['output']['PLY_file'] = ''
            self.settings['output']['color'] = False
            self.settings['output']['color_name'] = ''
            self.settings['output']['blender'] = False
            self.settings['output']['blender_path'] = ''

        if self.settings['output']['PLY_file']:
            initDir = os.path.dirname(self.settings['output']['PLY_file'])
        else:
            initDir = ""
        # added later, must be checked explicitly
        if 'calibration_scan' not in self.settings['output']:
            self.settings['output']['calibration_scan'] = 'scan_saved'
            self.settings['output']['calibrate'] = False

        # scan
        self.scan_name = wx.TextCtrl(self)
        self.scan_name.SetValue(self.settings['output']['scan'])
        self.scan_name.Bind(wx.EVT_TEXT, self.OnChange)
        bmp = get_show_layer_icon()
        addScan = wx.BitmapButton(self, bitmap=bmp, size=(bmp.GetWidth() + 12, bmp.GetHeight() + 8))
        addScan.Bind(wx.EVT_BUTTON, lambda evt: self._addLayer('scan'))

        self.calib_scan_name = wx.TextCtrl(self)
        self.calib_scan_name.SetValue(self.settings['output']['calibration_scan'])
        self.calib_scan_name.Bind(wx.EVT_TEXT, self.OnChange)
        bmp = get_show_layer_icon()
        addCScan = wx.BitmapButton(self, bitmap=bmp, size=(bmp.GetWidth() + 12, bmp.GetHeight() + 8))
        addCScan.Bind(wx.EVT_BUTTON, lambda evt: self._addLayer('calib'))

        # color
        self.ifColor = wx.CheckBox(self, label=_("Save color rasters (with postfixes _r, _g, _b):"))
        self.ifColor.SetValue(self.settings['output']['color'])
        self.ifColor.Bind(wx.EVT_CHECKBOX, self.OnChange)
        self.exportColor = Select(self, size=(-1, -1), type='raster')
        self.exportColor.SetValue(self.settings['output']['color_name'])
        self.exportColor.Bind(wx.EVT_TEXT, self.OnChange)
        bmp = get_show_layer_icon()
        self.addColor = wx.BitmapButton(self, bitmap=bmp, size=(bmp.GetWidth() + 12, bmp.GetHeight() + 8))
        self.addColor.Bind(wx.EVT_BUTTON, lambda evt: self._addLayer('color'))
        # Blender
        self.ifBlender = wx.CheckBox(self, label='')
        self.ifBlender.SetValue(self.settings['output']['blender'])
        self.ifBlender.Bind(wx.EVT_CHECKBOX, self.OnChange)
        initDirBlender = ''
        if self.settings['output']['blender_path']:
            initDirBlender = self.settings['output']['blender_path']
        self.blenderPath = filebrowse.DirBrowseButton(self, labelText="Export folder for Blender coupling:",
                                                      startDirectory=initDirBlender, newDirectory=True,
                                                      changeCallback=self.OnChange)

        # PLY
        self.ifPLY = wx.CheckBox(self, label="")
        self.ifPLY.SetValue(self.settings['output']['PLY'])
        self.ifPLY.Bind(wx.EVT_CHECKBOX, self.OnChange)
        self.exportPLY = filebrowse.FileBrowseButton(self, labelText="Export PLY:", fileMode=wx.FD_SAVE,
                                                     startDirectory=initDir, initialValue=self.settings['output']['PLY_file'],
                                                     changeCallback=self.OnChange)
        # must be called after all widgets are created
        self.blenderPath.SetValue(initDirBlender)

        mainSizer = wx.BoxSizer(wx.VERTICAL)
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(wx.StaticText(self, label="Name of scanned raster:"), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=5)
        sizer.Add(self.scan_name, proportion=1, flag=wx.EXPAND | wx.ALL, border=5)
        sizer.Add(addScan, proportion=0, flag=wx.EXPAND | wx.RIGHT | wx.TOP | wx.BOTTOM, border=5)
        mainSizer.Add(sizer, flag=wx.EXPAND | wx.ALL, border=5)
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(wx.StaticText(self, label="Name of calibration scan raster:"), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=5)
        sizer.Add(self.calib_scan_name, proportion=1, flag=wx.EXPAND | wx.ALL, border=5)
        sizer.Add(addCScan, proportion=0, flag=wx.EXPAND | wx.RIGHT | wx.TOP | wx.BOTTOM, border=5)
        mainSizer.Add(sizer, flag=wx.EXPAND | wx.ALL, border=5)
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(self.ifColor, flag=wx.ALIGN_CENTER_VERTICAL, border=5)
        sizer.Add(self.exportColor, proportion=1, flag=wx.ALIGN_CENTER_VERTICAL, border=5)
        sizer.Add(self.addColor, proportion=0, flag=wx.EXPAND | wx.ALL, border=5)
        mainSizer.Add(sizer, flag=wx.EXPAND | wx.ALL, border=5)
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(self.ifBlender, flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL | wx.LEFT, border=3)
        sizer.Add(self.blenderPath, flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, proportion=1, border=0)
        mainSizer.Add(sizer, flag=wx.EXPAND | wx.ALL, border=5)
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(self.ifPLY, flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL | wx.LEFT, border=3)
        sizer.Add(self.exportPLY, flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, proportion=1, border=0)
        mainSizer.Add(sizer, flag=wx.EXPAND | wx.ALL, border=5)
        self.SetSizer(mainSizer)
        mainSizer.Fit(self)

    def OnChange(self, event):
        self.settings['output']['scan'] = self.scan_name.GetValue()
        self.settings['output']['calibration_scan'] = self.calib_scan_name.GetValue()
        self.settings['output']['color'] = self.ifColor.IsChecked()
        self.settings['output']['color_name'] = self.exportColor.GetValue()
        self.settings['output']['blender'] = self.ifBlender.IsChecked()
        self.settings['output']['blender_path'] = self.blenderPath.GetValue()
        self.settings['output']['PLY'] = self.ifPLY.IsChecked()
        self.settings['output']['PLY_file'] = self.exportPLY.GetValue()
        self.settingsChanged.emit()

    def _addLayer(self, ltype):
        if not self.giface.GetLayerTree():
            return
        ll = self.giface.GetLayerList()
        if ltype == 'scan':
            raster = self.scan_name.GetValue()
            if not raster:
                return
            cmd = ['d.rast', 'map=' + raster]
            ll.AddLayer('raster', name=raster, checked=True, cmd=cmd)
        elif ltype == 'calib':
            raster = self.calib_scan_name.GetValue()
            if not raster:
                return
            cmd = ['d.rast', 'map=' + raster]
            ll.AddLayer('raster', name=raster, checked=True, cmd=cmd)
        elif ltype == 'color':
            name = self.exportColor.GetValue()
            if not name:
                return
            cmd = ['d.rgb', 'red={m}'.format(m=name + '_r'), 'green={m}'.format(m=name + '_g'), 'blue={m}'.format(m=name + '_b'), '-n']
            ll.AddLayer('rgb', name=name, checked=True, cmd=cmd)
