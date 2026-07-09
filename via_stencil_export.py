import pcbnew
import os
import wx
import tempfile
import shutil
import xml.etree.ElementTree as ET

class ViaStencilPlugin(pcbnew.ActionPlugin):
    def defaults(self):
        self.name = "Via Stencil Exporter (Laser & Gerber)"
        self.category = "Export"
        self.description = "Exportiert Vias, FIDs und Umriss parallel als perfektes Laser-SVG (rote Kontur, 0.01mm, reine Pfade) und als Gerber-Datei."
        self.show_toolbar_button = True
        self.icon_file_name = os.path.join(os.path.dirname(__file__), 'icon.png')

    def Run(self):
        board = pcbnew.GetBoard()
        board_file = board.GetFileName()
        
        if not board_file or not os.path.exists(board_file):
            wx.MessageBox("Das Layout muss vor dem Export gespeichert werden.\nBitte speichern Sie die Platine (Strg+S).", "Export abgebrochen", wx.OK | wx.ICON_WARNING)
            return
            
        temp_dir = tempfile.mkdtemp()
        temp_board_path = os.path.join(temp_dir, "temp_board.kicad_pcb")
        
        try:
            shutil.copy2(board_file, temp_board_path)
            temp_board = pcbnew.LoadBoard(temp_board_path)
            
            items_to_remove = []
            
            # 1. Alle Bauteile sammeln - AUSSER Fiducials (Passermarken)
            for fp in temp_board.Footprints():
                ref = fp.GetReference().upper()
                if not ref.startswith("FID"):
                    items_to_remove.append(fp)
                
            # 2. Alle Zonen (Kupferflächen) sammeln
            for zone in temp_board.Zones():
                items_to_remove.append(zone)
                
            # 3. Umriss (Edge.Cuts) auf Kupferebene schieben, Rest löschen
            for drawing in temp_board.Drawings():
                if drawing.GetLayer() == pcbnew.Edge_Cuts:
                    drawing.SetLayer(pcbnew.F_Cu)
                else:
                    items_to_remove.append(drawing)
                    
            if hasattr(temp_board, 'Texts'):
                for txt in temp_board.Texts():
                    items_to_remove.append(txt)
                    
            # 4. Leiterbahnen löschen, VIAS BEHALTEN
            for track in temp_board.Tracks():
                if not isinstance(track, pcbnew.PCB_VIA):
                    items_to_remove.append(track)
                    
            # Gesammeltes Aufräumen ausführen
            for item in items_to_remove:
                temp_board.Remove(item)
                
            # Ausgabeverzeichnis und Dateiname definieren
            out_dir = os.path.dirname(board_file)
            board_basename = os.path.basename(board_file)
            board_name_no_ext = os.path.splitext(board_basename)[0]
            export_filename = f"{board_name_no_ext}_LaserStencil"
            
            # ---------------------------------------------------------
            # EXPORT 1: REINE GERBER-DATEI (.gbr)
            # ---------------------------------------------------------
            pctl_gbr = pcbnew.PLOT_CONTROLLER(temp_board)
            popt_gbr = pctl_gbr.GetPlotOptions()
            popt_gbr.SetOutputDirectory(out_dir)
            popt_gbr.SetFormat(pcbnew.PLOT_FORMAT_GERBER)
            try:
                popt_gbr.SetDrillMarksType(0) # Keine Bohrlöcher plotten
            except:
                pass
                
            pctl_gbr.SetLayer(pcbnew.F_Cu)
            pctl_gbr.OpenPlotfile(export_filename, pcbnew.PLOT_FORMAT_GERBER, "Laser Stencil Gerber")
            pctl_gbr.PlotLayer()
            pctl_gbr.ClosePlot()
            
            # ---------------------------------------------------------
            # EXPORT 2: SVG-DATEI (.svg)
            # ---------------------------------------------------------
            pctl_svg = pcbnew.PLOT_CONTROLLER(temp_board)
            popt_svg = pctl_svg.GetPlotOptions()
            popt_svg.SetOutputDirectory(out_dir)
            popt_svg.SetFormat(pcbnew.PLOT_FORMAT_SVG)
            try:
                popt_svg.SetDrillMarksType(0)
                popt_svg.SetPlotBackground(False) # Verhindert ein riesiges KiCad-Hintergrundobjekt
            except:
                pass
            
            pctl_svg.SetLayer(pcbnew.F_Cu)
            pctl_svg.OpenPlotfile(export_filename, pcbnew.PLOT_FORMAT_SVG, "Laser Stencil SVG")
            pctl_svg.PlotLayer()
            pctl_svg.ClosePlot()
            
            # ---------------------------------------------------------
            # XML-NACHBEARBEITUNG: KREISE -> PFADE & REINE ROTE KONTUR
            # ---------------------------------------------------------
            svg_filepath = os.path.join(out_dir, f"{export_filename}.svg")
            if os.path.exists(svg_filepath):
                
                # Namespace registrieren, um "ns0:" Präfixe im XML zu verhindern
                ET.register_namespace('', "http://www.w3.org/2000/svg")
                tree = ET.parse(svg_filepath)
                root = tree.getroot()
                
                # 1. Alle alten, globalen <style> Blöcke restlos entfernen
                for parent in root.iter():
                    for child in list(parent):
                        if child.tag.endswith('style'):
                            parent.remove(child)
                            
                # Störende Attribute definieren
                bad_attrs = ['style', 'fill', 'stroke', 'stroke-width', 'class', 'opacity', 
                             'fill-opacity', 'stroke-opacity', 'stroke-linecap', 'stroke-linejoin']
                             
                # 2. Den gesamten XML-Baum durchlaufen
                for elem in root.iter():
                    tag_name = elem.tag.split('}')[-1]
                    
                    # Alte Formatierungen komplett löschen
                    for attr in bad_attrs:
                        if attr in elem.attrib:
                            del elem.attrib[attr]
                            
                    # ANFORDERUNG: Kreisobjekte in echte Pfade (path) konvertieren
                    if tag_name == 'circle':
                        cx = elem.get('cx')
                        cy = elem.get('cy')
                        r = elem.get('r')
                        if cx is not None and cy is not None and r is not None:
                            try:
                                f_cx, f_cy, f_r = float(cx), float(cy), float(r)
                                # Erzeugt einen mathematisch sauberen, geschlossenen SVG-Pfad aus zwei Kreisbögen
                                d_path = f"M {f_cx - f_r},{f_cy} A {f_r},{f_r} 0 1,0 {f_cx + f_r},{f_cy} A {f_r},{f_r} 0 1,0 {f_cx - f_r},{f_cy}"
                                elem.tag = '{http://www.w3.org/2000/svg}path'
                                elem.set('d', d_path)
                                del elem.attrib['cx']
                                del elem.attrib['cy']
                                del elem.attrib['r']
                                tag_name = 'path' # Tag-Typ für den nächsten Schritt aktualisieren
                            except:
                                pass
                                
                    # 3. Knallhartes Laser-Profil auf alle sichtbaren Geometrien anwenden
                    if tag_name in ['path', 'rect', 'polygon', 'polyline', 'line']:
                        # Wir setzen es als direkten Style UND als Einzel-Attribute, um Inkscape zu zwingen!
                        elem.set('style', 'fill:none; stroke:#FF0000; stroke-width:0.01mm;')
                        elem.set('fill', 'none')
                        elem.set('stroke', '#FF0000')
                        elem.set('stroke-width', '0.01mm')
                    elif tag_name in ['g', 'svg']:
                        # Auch Gruppen und Root-Tags dürfen standardmäßig NIEMALS schwarz füllen
                        elem.set('fill', 'none')

                # Datei sauber abspeichern
                tree.write(svg_filepath, encoding='utf-8', xml_declaration=True)

            # Professionelle Erfolgsmeldung für beide Dateien
            msg = (f"Export erfolgreich abgeschlossen!\n\n"
                   f"Folgende Dateien wurden in Ihrem Projektordner erzeugt:\n"
                   f"1. SVG: {export_filename}.svg (100% Pfade, 0.01mm rote Kontur)\n"
                   f"2. Gerber: {export_filename}.gbr (Industriestandard für Schablonen)")
            wx.MessageBox(msg, "Export erfolgreich", wx.OK | wx.ICON_INFORMATION)
            
        except Exception as e:
            wx.MessageBox(f"Während des Exports ist ein Fehler aufgetreten:\n{str(e)}", "Export fehlgeschlagen", wx.OK | wx.ICON_ERROR)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

ViaStencilPlugin().register()