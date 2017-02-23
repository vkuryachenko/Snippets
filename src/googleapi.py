import copy

from apiclient.discovery import build
from googleapiclient.errors import Error
from oauth2client.service_account import ServiceAccountCredentials

from httplib2 import Http

from django.utils.translation import ugettext_lazy as _


SPREADSHEET_TYPE = 'application/vnd.google-apps.spreadsheet'
FOLDER_TYPE = 'application/vnd.google-apps.folder'


class DublicationSpreadsheet(Error):
    pass


class SheetNotFound(Error):
    pass


class SpreadsheetNotFound(Error):
    pass


class ObjectNotFound(Error):
    pass


class Client(object):

    def __init__(self, json_key_file, scopes=None, folder=None, template=None):
        self.folder = folder
        self.template = template
        self.credentials = ServiceAccountCredentials.from_json_keyfile_name(
            json_key_file,
            scopes=scopes
        )
        self.http = self.credentials.authorize(Http())
        self.drive_service = build('drive', 'v3', http=self.http)
        self.sheet_service = build('sheets', 'v4', http=self.http)

    def get_file_properties(self, id_):
        """Return File/Folder properties by ID"""
        return self.drive_service.files().get(fileId=id_, fields='*').execute()

    def get_file_extended_properties(self, id_):
        """Return File/Folder extended properties by ID

           Additionally to 'get_file_properties' get full_name, owner,
           files(folder only) for Google Drive object(file, folder).

        """
        result = self.get_file_properties(id_)
        if not result:
            raise ObjectNotFound(
                _('File/Folder ID:"{}" not found.'.format(id_)))
        parents = result.get('parents')
        parent = self.get_file_properties(parents[0]) if parents else None
        files = []
        if result.get('mimeType') == FOLDER_TYPE:
            files = self.get_files(folder=id_)
        result['full_name'] = result.get('name')
        if parent:
            result['full_name'] = '{}/{}'.format(
                parent.get('name'), result.get('name'))
        owners = result.get('owners')
        if owners:
            result['owner'] = owners[0].get('displayName')
        result['files'] = dict([(file_.name, file_.id) for file_ in files])
        return result

    def get_files(self, name=None, mime_type=None,
                  folder=None, query=None):
        """Search or filter files in Google drive.

        Search files with query combining one or more search clauses.

        Keyword arguments:
        name -- (optional) file name.
        mime_type -- (optional) MIME type of the files.
        folder -- (optional) ID of the folder files location.
        query -- (optional) additional query string.
        For example:
            query="name contains '201?'".
        Query string allows to use wildcards (*, ?).
        See Google Drive APIs REST Search for Files.

        Return list of the File Class instances.

        """
        q = ''
        if mime_type:
            q = "mimeType = '{}'".format(mime_type)
        else:
            q = "mimeType contains ''"

        if name:
            q += " and name='{}'".format(self.escape(name))

        if folder:
            q += " and '{}' in parents".format(folder)

        if query:
            q += " and {}".format(self.escape(query))

        response = self.drive_service.files().list(
            q=q, fields='files(id,name,parents,mimeType,webViewLink)'
        ).execute()

        return [File(self, f) for f in response['files']]

    def escape(self, arg):
        return arg.replace('"', '\"').replace("'", "\'")

    def get_spreadsheets(self, name=None, folder=None,
                         name_filter=None, query=None):
        """Get List of Spreadsheet instances."""
        files = self.get_files(mime_type=SPREADSHEET_TYPE, folder=folder,
                               name=name, query=query)
        return [Spreadsheet(f) for f in files]

    def get_spreadsheet_properties(self, spreadsheetId):
        """ Get the metadata for a spreadsheet by ID.

        Args:
        spreadsheetId -- The ID of the file to get metadata for.

        Return:
        spreadsheetId -- The ID of the spreadsheet.
        properties -- object(SpreadsheetProperties)
                      Overall properties of a spreadsheet.
        sheets[] -- object(Sheet). The sheets that are part of a spreadsheet.
        namedRanges[] --  The named ranges defined in a spreadsheet.

        """
        return self.sheet_service.spreadsheets().get(
            spreadsheetId=spreadsheetId,
            fields='sheets.properties'
        ).execute()

    def open(self, title, folder=None):
        """Return Spreadsheet instance."""
        folder = folder or self.folder
        spreadsheets = self.get_spreadsheets(name=title, folder=folder)
        if len(spreadsheets) > 1:
            raise DublicationSpreadsheet(
                _('Duplicate spreadsheet {}'.format(title))
            )

        if not spreadsheets:
            return None

        return spreadsheets[0]

    def open_or_create(self, title):
        """Open existing spreadsheet or create new.

        Return Spreadsheet instance.

        """
        spreadsheets = self.get_spreadsheets(title)

        if len(spreadsheets) > 1:
            raise DublicationSpreadsheet(
                _('Duplicate spreadsheet {}'.format(title))
            )

        if spreadsheets:
            return spreadsheets[0]

        return self.create(title)

    def create(self, title, spreadsheetId=None, folder=None):
        """Create new spreadsheet.

        Copy template spreadsheet to the destination folder and call by title.

        Arg: title -- The name of the new spreadsheet.
        Keyword arguments:
        spreadsheetId -- ID of the source template spreadsheet,
                         default value: self.template.
        folder -- id of the destination folder, default value: self.folder

        Return Spreadsheet instance.

        """
        spreadsheetId = spreadsheetId or self.template
        folder = folder or self.folder

        response = self.drive_service.files().copy(
            fileId=spreadsheetId,
            body={'name': title, 'parents': [folder]},
            fields='id,name,parents,mimeType,webViewLink'
        ).execute()

        return Spreadsheet(File(self, response))

    def create_spreadsheets(self, titles):
        """Copy template spreadsheet to work folder by list of titles."""
        spreadsheets = [self.create_spreadsheet(title) for title in titles]
        return spreadsheets

    def empty_bin(self):
        """Delete spreadsheets in the service account's root(bin) folder."""
        for file_ in filter(lambda f: not f.parents,
                            self.get_files(mime_type=SPREADSHEET_TYPE)):
            self.delete(file_.id)

    def delete(self, spreadsheetId):
        self.drive_service.files().delete(fileId=spreadsheetId).execute()

    def create_template_spreadsheet(
            self, title, sheet_titles, folder, super_template):
        """Create new template spreadsheet with sheets base on prototype sheet.

        Args:
        title -- title of the new template spreadsheet.
        sheet_titles -- List titles sheets.
        folder -- folder for the new template.
        super_template -- spreadsheet with the prototype sheet.

        """
        sourceId = super_template
        folder = folder

        # delete destination file if exists
        for file_ in self.get_files(name=title, folder=folder):
            self.delete(file_.id)
        self.empty_bin()
        # create new destination file
        dest = self.create(title, spreadsheetId=sourceId, folder=folder)

        # delete sheets except first
        requests = []
        for sheet in dest.sheets[1:]:
            requests.append({
                'deleteSheet': {
                    'sheetId': sheet.id
                }
            })
        dest.batch_update(requests)

        # copy and rename sheets
        sheetId = dest.sheets[0].id
        for sh_title in sheet_titles:
            # copy sheet
            sheet = self.sheet_service.spreadsheets().sheets().copyTo(
                spreadsheetId=dest.id,
                sheetId=sheetId,
                body={'destinationSpreadsheetId': dest.id},
                fields='sheetId,title'
            ).execute()

            # rename new sheet
            sheetId = sheet.get('sheetId')
            requests = []
            requests.append({
                'updateSheetProperties': {
                    'properties': {
                        'sheetId': sheetId, 'title': sh_title, 'hidden': True,
                    },
                    'fields': 'title, hidden'
                }
            })
            dest.batch_update(requests)

        return dest


class File(object):

    """A class for google drive objects (files/folders)."""

    def __init__(self, client, response):

        """ init from google drive API response body """

        self.client = client
        self.id = response['id']
        self.name = response['name']
        self.parents = response.get('parents', [])
        self.mimeType = response['mimeType']
        self.webViewLink = response.get('webViewLink', None)

    def __repr__(self):
        return '<{} "{}" id:"{}" type:"{}" parents:{}>'.format(
            self.__class__.__name__,
            self.name,
            self.id,
            self.mimeType,
            self.parents
        )


class Spreadsheet(object):

    """ A class for a spreadsheet object."""

    def __init__(self, file_):
        self.file = file_
        self.root_folder = self.client.folder in self.file.parents

        spreadsheet = self.client.get_spreadsheet_properties(self.file.id)

        self.sheets = [
            Sheet(
                self,
                s['properties']['sheetId'],
                s['properties']['title'],
                s['properties'].get('hidden', False)
            )
            for s in spreadsheet['sheets']
        ]

    def __repr__(self):
        sheets = [sh.title for sh in self.sheets if not sh.hidden]
        return '<{} "{}" id:"{}" sheets:{}>'.format(
            self.__class__.__name__, self.file.name,
            self.file.id, '|'.join(sheets)
        )

    @property
    def id(self):
        """Id of a spreadsheet."""
        return self.file.id

    @property
    def title(self):
        """Title of a spreadsheet."""
        return self.file.name

    @property
    def link(self):
        """Public web link to spreadsheet."""
        return self.file.webViewLink

    @property
    def client(self):
        """Reference to api client."""
        return self.file.client

    def batch_update(self, requests):
        """Call Google Sheets API Method spreadsheets.batchUpdate.

        Arg: requests for execution.

        """
        if requests:
            return self.client.sheet_service.spreadsheets().batchUpdate(
                spreadsheetId=self.file.id,
                body={'requests': requests}
            ).execute()

    def update_sheet_property(self, titles, property_, value):
        """Update property of the sheet[s.

        Args:
        titles -- list titles of the sheets, whose properties will be update.
        propery_ -- the name of property for updating.
        value -- new value of the property.

        Available properties for updating:
        title --The name of the sheet.
        index -- The index of the sheet within the spreadsheet.
        sheetType -- The kind of sheet, enum('GRID', 'OBJECT').
        gridProperties -- Additional properties of the sheet,
                          if this sheet is a grid.
        hidden --  boolean, True if the sheet is hidden, False if it's visible.
        tabColor --The color of the tab.
        rightToLeft -- boolean, True if the sheet is an RTL sheet
                       instead of an LTR sheet.
        For detailed information see:
             Google Sheets API UpdateSheetPropertiesRequest.

        """
        properties = {'properties': {'sheetId': ''}, 'fields': property_}
        properties['properties'][property_] = value

        requests = []
        for sh in filter(lambda sh: sh.title in titles, self.sheets):
            prop = copy.deepcopy(properties)
            prop['properties']['sheetId'] = sh.id
            requests.append({'updateSheetProperties': prop})
        self.batch_update(requests)

    def sheet(self, title):
        """ Return Sheet instance by title"""
        sheets = [sheet for sheet in self.sheets if sheet.title == title]
        if not sheets:
            raise SheetNotFound(_('Sheet {} not found.'.format(title)))
        return sheets[0]


class Sheet(object):

    """A class for sheet object."""

    def __init__(self, spreadsheet, idSheet, title, hidden):
        self.spreadsheet = spreadsheet
        self.id = idSheet
        self.title = title
        self.hidden = hidden

    def rows_range(self, start, count):
        return {
            'sheetId': self.id,
            'dimension': 'ROWS',
            'startIndex': start,
            'endIndex': start + count
        }

    def insert_rows(self, start, count=1, before=False):
        """Insert new 'count' rows starting with the 'start' position.

        Args:
        start -- Starting position.
        count -- The number of the new rows.
        before -- Whether dimension properties should be extended
        from the dimensions before or after the newly inserted dimensions.

        """
        self.spreadsheet.batch_update(({
            'insertDimension': {
                'range': self.rows_range(start, count),
                'inheritFromBefore': before
            }
        },))

    def delete_rows(self, start, count=1):
        """Delete 'count' rows starting with the 'start' position."""
        self.spreadsheet.batch_update(({
            'deleteDimension': {'range': self.rows_range(start-1, count)}},))

    def put_rows(self, start, values):
        """Insert values by rows

        Insert a two-dimensional array of values starting col:1 row:start

        """
        value_range = []
        row = start
        for value in values:
            sheet_range = "'{}'!{}:{}".format(self.title, row, row)
            value_range.append({
                'range': sheet_range,
                'values': [value],
                'majorDimension': 'ROWS'
            })
            row += 1

        body = {
          'valueInputOption': 'USER_ENTERED',
          'data': value_range,
        }
        return (
            self.spreadsheet.client.sheet_service.spreadsheets().values()
            .batchUpdate(spreadsheetId=self.spreadsheet.id, body=body)
            .execute()
        )

    def get_cells_values(self, cells):
        cells = "'{}'!{}".format(self.title, cells)
        return (
            self.spreadsheet.client.sheet_service.spreadsheets().values()
            .get(spreadsheetId=self.spreadsheet.id, range=cells).execute()
            .get('values', [])
        )
